"""电桥档：登记、检索、删除，以及档与档之间阻值互不串扰。"""
from app.bridge.topology import ArmSet
from app.presets import PresetStore


def test_register_get_list_delete():
    store = PresetStore()
    store.register("std-1k", ArmSet(1000.0, 1000.0, 1000.0, 1000.0), "基准档")
    store.register("ratio-10", ArmSet(100.0, 100.0, 10.0, 10.0))
    assert [p.name for p in store.list()] == ["ratio-10", "std-1k"]
    assert store.get("std-1k").description == "基准档"
    assert store.get("missing") is None
    assert store.delete("std-1k") is True
    assert store.delete("std-1k") is False
    assert [p.name for p in store.list()] == ["ratio-10"]


def test_presets_are_independent():
    """两套档并存时，覆盖其中一套的四臂阻值不会串到另一套名下。"""
    store = PresetStore()
    store.register("alpha", ArmSet(100.0, 200.0, 300.0, 400.0))
    store.register("beta", ArmSet(1000.0, 1000.0, 1000.0, 1000.0))
    store.register("alpha", ArmSet(1.0, 2.0, 3.0, 4.0))  # 整体替换 alpha
    assert store.get("alpha").arms == ArmSet(1.0, 2.0, 3.0, 4.0)
    assert store.get("beta").arms == ArmSet(1000.0, 1000.0, 1000.0, 1000.0)
