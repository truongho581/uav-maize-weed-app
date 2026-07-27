from pathlib import Path

from uav_crop_analysis.inference import ModelRegistry, ModelTask


REGISTRY = Path(__file__).parents[1] / "models/model_inventory.json"


def test_model_contract_keeps_weed_out_of_instance_counting() -> None:
    registry = ModelRegistry.from_file(REGISTRY)
    instance = registry.list_models(ModelTask.MAIZE_INSTANCE)

    assert instance
    assert all("weed" not in model.class_names for model in instance)
    assert all(model.target_classes == ("maize2", "maize4", "maize6") for model in instance)


def test_semantic_business_target_is_weed_only() -> None:
    registry = ModelRegistry.from_file(REGISTRY)
    semantic = registry.list_models(ModelTask.SEMANTIC)

    assert semantic
    assert all(model.target_classes == ("weed",) for model in semantic)
