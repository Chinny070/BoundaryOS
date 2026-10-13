import pytest


@pytest.fixture(autouse=True)
def direct_mode_pickling_check(direct_vm):
    direct_vm.check_pickling = True
