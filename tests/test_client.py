from pyftms.client.client import FitnessMachine


class ResetTracker:
    def __init__(self):
        self.calls = 0

    def reset(self):
        self.calls += 1


def test_on_disconnect_can_be_called_multiple_times():
    disconnects = []
    machine = object.__new__(FitnessMachine)
    machine._updater = ResetTracker()
    machine._controller = ResetTracker()
    machine._disconnect_cb = disconnects.append
    machine._cli = object()

    machine._on_disconnect(None)
    machine._on_disconnect(None)

    assert machine._updater.calls == 2
    assert machine._controller.calls == 2
    assert disconnects == [machine, machine]
    assert not hasattr(machine, "_cli")
