"""Packaged architecture definitions matching the trusted training checkpoints."""

from __future__ import annotations

from typing import Any

from uav_crop_analysis.errors import DependencyUnavailableError, ModelManifestError


def build_semantic_model(family: str, num_classes: int, norm: str = "gn") -> Any:
    if family == "attention_unet":
        from .attention_unet import AttentionUNet

        return AttentionUNet(in_channels=3, num_classes=num_classes, norm=norm)
    if family == "deeplabv3plus_resnet50":
        from .deeplabv3plus import deeplabv3plus_resnet50

        return deeplabv3plus_resnet50(
            num_classes=num_classes,
            output_stride=8,
            pretrained_backbone=False,
        )
    if family == "segformer_b0":
        try:
            from transformers import SegformerConfig, SegformerForSemanticSegmentation
        except ImportError as exc:
            raise DependencyUnavailableError(
                "SegFormer requires the optional 'transformers' dependency"
            ) from exc
        id2label = {index: str(index) for index in range(num_classes)}
        label2id = {str(index): index for index in range(num_classes)}
        config = SegformerConfig(
            num_labels=num_classes,
            id2label=id2label,
            label2id=label2id,
        )
        return SegformerForSemanticSegmentation(config)
    raise ModelManifestError(f"unsupported semantic model family: {family}")


__all__ = ["build_semantic_model"]
