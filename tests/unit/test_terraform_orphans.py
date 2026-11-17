"""Tests for the pure orphaned-state helpers (#1459)."""

from pathlib import Path

from infrafoundry.core.runners import terraform_orphans as orph

TF = """resource "terraform_data" "ova_vm_fw_test_a" {
  triggers_replace = {
    vmid = "105"
  }
}

resource "proxmox_virtual_environment_vm" "web_01" {
  name  = "web-01"
  vm_id = 110
  clone {
    vm_id = 9000
  }
}

resource "proxmox_virtual_environment_vm" "no_id" {
  name = "x"
}

module "ts_web" {
  source = "./m"
}
"""


def test_normalize_state_address() -> None:
    assert orph.normalize_state_address("data.x.y") is None
    assert orph.normalize_state_address("a.b[0]") == "a.b"
    assert orph.normalize_state_address('a.b["k"]') == "a.b"
    assert orph.normalize_state_address("module.ts_web[0].x.y") == "module.ts_web"
    assert orph.normalize_state_address("module.ts_web.x.y") == "module.ts_web"


def test_orphaned_addresses(tmp_path: Path) -> None:
    (tmp_path / "main.tf").write_text(TF)
    declared = {"terraform_data.ova_vm_fw_test_a", "proxmox_virtual_environment_vm.web_01"}
    modules = orph.declared_modules(tmp_path)
    assert modules == {"ts_web"}
    state = [
        "terraform_data.ova_vm_fw_test_a",
        "terraform_data.ova_vm_fw_test",
        "terraform_data.ova_vm_fw_test",
        "data.proxmox_x.y",
        'proxmox_virtual_environment_vm.web_01["a"]',
        "module.ts_web[0].x.y",
        "module.gone.x.y",
    ]
    assert orph.orphaned_addresses(state, declared, modules) == [
        "terraform_data.ova_vm_fw_test",
        "module.gone.x.y",
    ]


def test_declared_vm_ids(tmp_path: Path) -> None:
    (tmp_path / "main.tf").write_text(TF)
    assert orph.declared_vm_ids(tmp_path) == {
        "terraform_data.ova_vm_fw_test_a": "105",
        "proxmox_virtual_environment_vm.web_01": "110",
    }


def test_state_vm_ids() -> None:
    show = {
        "values": {
            "root_module": {
                "resources": [
                    {"address": "a.b", "mode": "managed", "values": {"vm_id": 7}},
                    {
                        "address": "terraform_data.c",
                        "mode": "managed",
                        "values": {"triggers_replace": {"vmid": "105"}},
                    },
                    {"address": "data.d", "mode": "data", "values": {"vm_id": 9}},
                ],
                "child_modules": [
                    {"resources": [{"address": "m.e", "mode": "managed", "values": {"vm_id": 8}}]}
                ],
            }
        }
    }
    assert orph.state_vm_ids(show) == {"a.b": "7", "terraform_data.c": "105", "m.e": "8"}
    assert orph.state_vm_ids({}) == {}


def test_find_vmid_collisions() -> None:
    assert orph.find_vmid_collisions({"n.a": "105", "n.b": "106"}, {"o.a": "105"}) == [
        ("n.a", "105", "o.a")
    ]


def test_messages() -> None:
    warn = orph.orphan_warning("proxmox", "dev", ["o.a"], filtered=True)
    assert "o.a" in warn and "leaves them in place" in warn
    assert "destroys them" in orph.orphan_warning("proxmox", None, ["o.a"], filtered=False)
    msg = orph.collision_message("proxmox", "dev", [("n.a", "105", "o.a")])
    assert "n.a" in msg and "105" in msg and "o.a" in msg
    assert "foundry infra destroy --env dev -p" in msg
