# Copyright 2025, Sergey Dudanov
# SPDX-License-Identifier: Apache-2.0


class FtmsError(Exception):
    """Base FTMS error"""


class CharacteristicNotFound(FtmsError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Mandatory characteristic '{name}' not found.")


class NotFitnessMachineError(FtmsError):
    """
    An exception if the FTMS service is not supported by the Bluetooth device.

    May be raised in `get_machine_type_from_service_data` and `get_client`
    functions if advertisement data was passed as an argument.
    """

    def __init__(
        self, data: bytes | None = None, reason: str | None = None
    ) -> None:
        if reason is None and data is None:
            reason = "No FTMS service data"
        elif reason is None:
            reason = f"Wrong FTMS service data: '{data.hex(" ").upper()}'"

        super().__init__(f"Device is not Fitness Machine. {reason}.")
