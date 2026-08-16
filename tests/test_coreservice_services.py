"""CI-safe tests for the gestd Services adapter — the model->property-bag
converters (pure) and the contract shape. The variant packing + live systemctl
reads are exercised by the round-trip on a systemd host."""

from gest.core.services.model import Service, ServiceDetail
from gest.coreservice import services_adapter as adapter
from gest.ipc import core_contract


def test_service_to_dict_shape_and_enabled_running():
    s = Service(name="sshd.service", status="active", enabled_state="enabled",
                sub_state="running", description="OpenSSH")
    d = adapter.service_to_dict(s)
    assert d["name"] == "sshd.service" and d["status"] == "active"
    assert d["enabled_state"] == "enabled" and d["sub_state"] == "running"
    assert d["enabled"] is True and d["running"] is True and d["masked"] is False
    assert set(d) == {"name", "status", "sub_state", "enabled_state",
                      "enabled", "running", "masked", "description"}


def test_service_to_dict_inactive_and_not_enabled():
    d = adapter.service_to_dict(Service(name="foo.service"))       # defaults
    assert d["status"] == "inactive"
    assert d["enabled"] is False and d["running"] is False and d["enabled_state"] == "disabled"


def test_service_to_dict_masked():
    d = adapter.service_to_dict(Service(name="x.service", enabled_state="masked"))
    assert d["masked"] is True and d["enabled"] is False


def test_detail_to_dict_scalars_and_dep_lists():
    det = ServiceDetail(name="sshd.service", description="OpenSSH server",
                        requires=["sysinit.target"], wants=["network.target"],
                        after=["network.target"], required_by=["multi-user.target"],
                        status="active", enabled_state="enabled", load_state="loaded")
    d = adapter.detail_to_dict(det)
    assert d["description"] == "OpenSSH server"
    assert d["requires"] == ["sysinit.target"] and d["wants"] == ["network.target"]
    assert d["after"] == ["network.target"] and d["required_by"] == ["multi-user.target"]
    assert d["status"] == "active" and d["running"] is True
    assert d["enabled_state"] == "enabled" and d["enabled"] is True and d["load_state"] == "loaded"


def test_services_contract_shape():
    assert core_contract.SERVICES_CORE_IFACE == "org.gentoo.gest.core1.Services"
    assert core_contract.SERVICES_CORE_PATH == "/org/gentoo/gest/core/Services"
