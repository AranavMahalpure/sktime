#  Copyright (c) 2024, Salesforce, Inc.
#  SPDX-License-Identifier: Apache-2
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import abc

import torch
from einops import rearrange
from jaxtyping import Float, Int
from torch import nn


class AttentionBias(nn.Module, abc.ABC):
    def __init__(
        self,
        dim: int,
        num_heads: int,
        num_groups: int,
    ):
        super().__init__()
        assert num_heads > 0 and dim % num_heads == 0
        assert (num_heads % num_groups == 0) and (num_heads >= num_groups)

        self.num_heads = num_heads
        self.num_groups = num_groups
        self.heads_per_group = num_heads // num_groups
        self.head_dim = dim // num_heads

    @abc.abstractmethod
    def forward(
        self,
        query: Float[torch.Tensor, "*batch group hpg q_len dim"],
        key: Float[torch.Tensor, "*batch group hpg kv_len dim"],
        query_id: Int[torch.Tensor, "*batch 1 1 q_len"],
        kv_id: Int[torch.Tensor, "*batch 1 1 kv_len"],
    ) -> Float[torch.Tensor, "*batch #group #hpg q_len kv_len"]: ...


class BinaryAttentionBias(AttentionBias):
    def __init__(self, dim: int, num_heads: int, num_groups: int):
        super().__init__(dim, num_heads, num_groups)
        self.emb = nn.Embedding(num_embeddings=2, embedding_dim=self.num_heads)

    def forward(
        self,
        query: Float[torch.Tensor, "*batch group hpg q_len dim"],
        key: Float[torch.Tensor, "*batch group hpg kv_len dim"],
        query_id: Int[torch.Tensor, "*batch 1 1 q_len"],
        kv_id: Int[torch.Tensor, "*batch 1 1 kv_len"],
    ) -> Float[torch.Tensor, "*batch #group #hpg q_len kv_len"]:
        ind = torch.eq(query_id.unsqueeze(-1), kv_id.unsqueeze(-2))
        weight = rearrange(self.emb.weight, "two num_heads -> two num_heads 1 1")
        bias = rearrange(  # try to avoid advanced indexing
            ~ind * weight[:1] + ind * weight[1:],
            "... 1 (group hpg) q_len kv_len -> ... group hpg q_len kv_len",
            group=self.num_groups,
            hpg=self.heads_per_group,
        )
        return bias