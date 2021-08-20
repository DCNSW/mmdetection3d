# Copyright (c) OpenMMLab. All rights reserved.
from mmcv.runner import BaseModule, auto_fp16
from torch import nn as nn

from mmdet3d.ops import DGCNNFAModule, DGCNNGFModule
from mmdet.models import BACKBONES


@BACKBONES.register_module()
class DGCNN(BaseModule):
    """Backbone network for DGCNN.

    Args:
        in_channels (int): Input channels of point cloud.
        num_samples (tuple[int]): The number of samples for knn or ball query
            in each GF module.
        knn_modes (tuple[str]): If knn, mode of KNN of each GF module.
        radius (tuple[float]): Sampling radii of each GF module.
        gf_channels (tuple[tuple[int]]): Out channels of each mlp in GF module.
        fa_channels (tuple[int]): Out channels of each mlp in FA module.
        act_cfg (dict, optional): Config of activation layer.
            Default: dict(type='ReLU').
    """

    def __init__(self,
                 in_channels,
                 num_samples=(20, 20, 20),
                 knn_modes=['D-KNN', 'F-KNN', 'F-KNN'],
                 radius=(None, None, None),
                 gf_channels=((64, 64), (64, 64), (64, )),
                 fa_channels=(1024, ),
                 act_cfg=dict(type='ReLU'),
                 init_cfg=None):
        super().__init__(init_cfg=init_cfg)
        self.num_gf = len(gf_channels)

        assert len(num_samples) == len(knn_modes) == len(radius) == len(
            gf_channels)

        self.GF_modules = nn.ModuleList()
        gf_in_channel = in_channels * 2
        skip_channel_list = [gf_in_channel]  # input channel list

        for gf_index in range(self.num_gf):
            cur_gf_mlps = list(gf_channels[gf_index])
            cur_gf_mlps = [gf_in_channel] + cur_gf_mlps
            gf_out_channel = cur_gf_mlps[-1]

            self.GF_modules.append(
                DGCNNGFModule(
                    mlp_channels=cur_gf_mlps,
                    num_sample=num_samples[gf_index],
                    knn_mode=knn_modes[gf_index],
                    radius=radius[gf_index],
                    act_cfg=act_cfg))
            skip_channel_list.append(gf_out_channel)
            gf_in_channel = gf_out_channel * 2

        fa_in_channel = sum(skip_channel_list[1:])
        cur_fa_mlps = list(fa_channels)
        cur_fa_mlps = [fa_in_channel] + cur_fa_mlps

        self.FA_module = DGCNNFAModule(
            mlp_channels=cur_fa_mlps, act_cfg=act_cfg)

    @auto_fp16(apply_to=('points', ))
    def forward(self, points):
        """Forward pass.

        Args:
            points (torch.Tensor): point coordinates with features,
                with shape (B, N, in_channels).

        Returns:
            dict[str, list[torch.Tensor]]: Outputs after GF and FA modules.

                - gf_points (list[torch.Tensor]): Outputs after each GF module.
                - fa_points (torch.Tensor): Outputs after FA module.
        """
        gf_points = [points]

        for i in range(self.num_gf):
            cur_points = self.GF_modules[i](gf_points[i])
            gf_points.append(cur_points)

        fa_points = self.FA_module(gf_points)

        out = dict(gf_points=gf_points, fa_points=fa_points)
        return out