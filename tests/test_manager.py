from pyftms.client.backends import SetupEvent, UpdateEvent
from pyftms.client.manager import PropertiesManager


def test_properties_returns_stable_snapshot():
    manager = PropertiesManager()
    manager._on_event(UpdateEvent("update", {"speed_instant": 3.0}))

    properties = manager.properties
    iterator = iter(properties.items())
    assert next(iterator) == ("speed_instant", 3.0)

    manager._on_event(UpdateEvent("update", {"cadence_instant": 90.0}))

    assert list(iterator) == []
    assert dict(properties) == {"speed_instant": 3.0}
    assert manager.properties["cadence_instant"] == 90.0


def test_settings_returns_stable_snapshot():
    manager = PropertiesManager()
    manager._on_event(
        SetupEvent(
            event_id="setup",
            event_data={"target_resistance": 5.0},
            event_source="callback",
        )
    )

    settings = manager.settings
    iterator = iter(settings.items())
    assert next(iterator) == ("target_resistance", 5.0)

    manager._on_event(
        SetupEvent(
            event_id="setup",
            event_data={"target_power": 120},
            event_source="callback",
        )
    )

    assert list(iterator) == []
    assert dict(settings) == {"target_resistance": 5.0}
    assert manager.settings["target_power"] == 120
