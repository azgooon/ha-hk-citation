"""Binary sensor platform for HK Citation Health Monitor."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HKCitationCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up HK Citation binary sensors from a config entry."""
    coordinator: HKCitationCoordinator = entry.runtime_data

    added_uuids: set[str] = set()

    @callback
    def _async_add_new_speakers(new_uuids: set[str]) -> None:
        entities = []
        for uuid in new_uuids:
            if uuid not in added_uuids:
                added_uuids.add(uuid)
                entities.append(HKCitationHealthSensor(coordinator, uuid))
        if entities:
            async_add_entities(entities)

    coordinator.register_new_speaker_callback(_async_add_new_speakers)

    if coordinator.data and coordinator.data.get("speakers"):
        _async_add_new_speakers(set(coordinator.data["speakers"].keys()))


class HKCitationHealthSensor(
    CoordinatorEntity[HKCitationCoordinator], BinarySensorEntity
):
    """Binary sensor that reports the health of an HK Citation speaker."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_name = "Health"

    def __init__(self, coordinator: HKCitationCoordinator, uuid: str) -> None:
        """Initialize the health sensor."""
        super().__init__(coordinator)
        self._uuid = uuid
        self._attr_unique_id = f"hk_citation_{uuid}"

    @property
    def _speaker_data(self) -> dict | None:
        """Return the speaker data from the coordinator, or None."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("speakers", {}).get(self._uuid)

    @property
    def available(self) -> bool:
        """Return True if the speaker is present in the latest scan data."""
        return self._speaker_data is not None and super().available

    @property
    def is_on(self) -> bool | None:
        """Return True if the speaker is healthy, False if frozen."""
        data = self._speaker_data
        if data is None:
            return None
        return data["healthy"]

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        data = self._speaker_data
        if data is None:
            return {}
        return {
            "response_time_ms": data["response_time_ms"],
            "ip_address": data["ip"],
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the speaker."""
        data = self._speaker_data
        name = data["name"] if data else f"HK Citation {self._uuid[:8]}"
        model = data.get("model", "HK Citation") if data else "HK Citation"
        return DeviceInfo(
            identifiers={(DOMAIN, self._uuid)},
            name=name,
            manufacturer="Harman Kardon",
            model=model,
        )
