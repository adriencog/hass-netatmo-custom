"""Support for Netatmo alarm control panel."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import cast

from pyatmo.modules.netatmo import NIS, NACamera

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityDescription,
    AlarmControlPanelEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_ALARM_ARMED_AWAY,
    STATE_ALARM_ARMED_HOME,
    STATE_ALARM_DISARMED,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_URL_SECURITY, NETATMO_CREATE_SIREN_ALARM_CONTROL_PANEL
from .data_handler import HOME, SIGNAL_NAME, NetatmoDevice
from .entity import NetatmoModuleEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class NetatmoAlarmControlPanelEntityDescription(AlarmControlPanelEntityDescription):
    """Describe an Netatmo Alarm control panel entity."""

    netatmo_name: str
    netatmo_alarm_states: list


ALARM_TYPE = NetatmoAlarmControlPanelEntityDescription(
    key="netatmo_alarm",
    netatmo_name="alarm",
    netatmo_alarm_states=[
        None,
        STATE_ALARM_DISARMED,
        STATE_ALARM_ARMED_AWAY,
        STATE_ALARM_ARMED_HOME,
    ],
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Netatmo alarm platform."""

    @callback
    def _create_entity(netatmo_device: NetatmoDevice) -> None:
        entity = NetatmoAlarmEntity(netatmo_device, ALARM_TYPE)
        async_add_entities([entity])

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, NETATMO_CREATE_SIREN_ALARM_CONTROL_PANEL, _create_entity
        )
    )


class NetatmoAlarmEntity(NetatmoModuleEntity, AlarmControlPanelEntity):
    """Representation of an Ezviz alarm control panel."""

    _attr_configuration_url = CONF_URL_SECURITY

    entity_description: NetatmoAlarmControlPanelEntityDescription
    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = AlarmControlPanelEntityFeature.ARM_AWAY
    _attr_code_arm_required = False
    _signal_name: str

    def __init__(
        self,
        device: NetatmoDevice,
        description: NetatmoAlarmControlPanelEntityDescription,
    ) -> None:
        """Initialize a Netatmo alarm control panel."""
        super().__init__(device)
        self.entity_description = description
        self._attr_unique_id = f"{self.device.entity_id}-{description.key}"
        self._attr_translation_key = description.netatmo_name
        self._signal_name = f"{HOME}-{self.home.entity_id}"
        self._publishers.extend(
            [
                {
                    "name": HOME,
                    "home_id": self.home.entity_id,
                    SIGNAL_NAME: self._signal_name,
                },
            ]
        )

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command."""
        person_ids = list(self.home.persons.keys())
        await self.home.async_set_persons_home(person_ids)
        for person in self.home.persons.values():
            person.out_of_sight = False
        self.data_handler.notify(self._signal_name)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command."""
        await self.home.async_set_persons_away()
        for person in self.home.persons.values():
            person.out_of_sight = True
        self.data_handler.notify(self._signal_name)

    @callback
    def async_update_callback(self) -> None:
        """Update the entity's state."""
        self._attr_available = self.is_camera_monitoring and self.is_siren_monitoring
        if self.is_house_empty:
            self._attr_state = STATE_ALARM_ARMED_AWAY
        else:
            self._attr_state = STATE_ALARM_DISARMED
        self.async_write_ha_state()

    @property
    def is_house_empty(self) -> bool:
        """Checks if all people are out of sight."""
        persons_out_of_sight = [p.out_of_sight for p in self.home.persons.values()]
        return all(persons_out_of_sight)

    @property
    def is_camera_monitoring(self) -> bool:
        """Checks if camera is monitoring."""
        if parent_module_id := self.device.bridge:
            if parent_module := self.home.modules.get(parent_module_id):
                if camera := cast(NACamera, parent_module):
                    return camera.monitoring or False
        return False

    @property
    def is_siren_monitoring(self) -> bool:
        """Checks if siren is monitoring."""
        if siren := cast(NIS, self.device):
            return siren.monitoring or False
        return False
