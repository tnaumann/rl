# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import torch
from torchrl.data.tensor_specs import (
    NdUnboundedContinuousTensorSpec,
    NdBoundedTensorSpec,
    CompositeSpec,
    MultOneHotDiscreteTensorSpec,
    BinaryDiscreteTensorSpec,
    BoundedTensorSpec,
    UnboundedContinuousTensorSpec,
    OneHotDiscreteTensorSpec,
)
from torchrl.data.tensordict.tensordict import _TensorDict
from torchrl.envs.common import _EnvClass

spec_dict = {
    "bounded": BoundedTensorSpec,
    "one_hot": OneHotDiscreteTensorSpec,
    "unbounded": UnboundedContinuousTensorSpec,
    "ndbounded": NdBoundedTensorSpec,
    "ndunbounded": NdUnboundedContinuousTensorSpec,
    "binary": BinaryDiscreteTensorSpec,
    "mult_one_hot": MultOneHotDiscreteTensorSpec,
    "composite": CompositeSpec,
}

default_spec_kwargs = {
    BoundedTensorSpec: {"minimum": -1.0, "maximum": 1.0},
    OneHotDiscreteTensorSpec: {"n": 7},
    UnboundedContinuousTensorSpec: {},
    NdBoundedTensorSpec: {"minimum": -torch.ones(4), "maxmimum": torch.ones(4)},
    NdUnboundedContinuousTensorSpec: {
        "shape": [
            7,
        ]
    },
    BinaryDiscreteTensorSpec: {"n": 7},
    MultOneHotDiscreteTensorSpec: {"nvec": [7, 3, 5]},
    CompositeSpec: {},
}


def make_spec(spec_str):
    target_class = spec_dict[spec_str]
    return target_class(**default_spec_kwargs[target_class])


class _MockEnv(_EnvClass):
    def __init__(self, seed: int = 100):
        super().__init__(
            device="cpu",
            dtype=torch.float,
        )
        self.set_seed(seed)

    @property
    def maxstep(self):
        return self.counter

    def set_seed(self, seed: int) -> int:
        self.seed = seed
        self.counter = seed - 1
        return seed


class DiscreteActionVecMockEnv(_MockEnv):
    size = 7
    observation_spec = NdUnboundedContinuousTensorSpec(shape=torch.Size([size]))
    action_spec = OneHotDiscreteTensorSpec(7)
    reward_spec = UnboundedContinuousTensorSpec()
    from_pixels = False

    out_key = "observation"

    def _get_in_obs(self, obs):
        return obs

    def _get_out_obs(self, obs):
        return obs

    def _reset(self, tensor_dict: _TensorDict) -> _TensorDict:
        self.counter += 1
        state = torch.zeros(self.size) + self.counter
        tensor_dict = tensor_dict.select().set(self.out_key, self._get_out_obs(state))
        tensor_dict.set("done", torch.zeros(*tensor_dict.shape, 1, dtype=torch.bool))
        return tensor_dict

    def _step(
        self,
        tensor_dict: _TensorDict,
    ) -> _TensorDict:
        tensor_dict = tensor_dict.to(self.device)
        a = tensor_dict.get("action")
        assert (a.sum(-1) == 1).all()
        assert not self.is_done, "trying to execute step in done env"

        obs = (
            self._get_in_obs(self.current_tensordict.get(self.out_key))
            + a / self.maxstep
        )
        tensor_dict = tensor_dict.select()  # empty tensordict
        tensor_dict.set("next_" + self.out_key, self._get_out_obs(obs))
        done = torch.isclose(obs, torch.ones_like(obs) * (self.counter + 1))
        reward = done.any(-1).unsqueeze(-1)
        done = done.all(-1).unsqueeze(-1)
        tensor_dict.set("reward", reward.to(torch.float))
        tensor_dict.set("done", done)
        return tensor_dict


class ContinuousActionVecMockEnv(_MockEnv):
    size = 7
    observation_spec = NdUnboundedContinuousTensorSpec(shape=torch.Size([size]))
    action_spec = NdBoundedTensorSpec(-1, 1, (7,))
    reward_spec = UnboundedContinuousTensorSpec()
    from_pixels = False

    out_key = "observation"

    def _get_in_obs(self, obs):
        return obs

    def _get_out_obs(self, obs):
        return obs

    def _reset(self, tensor_dict: _TensorDict) -> _TensorDict:
        self.counter += 1
        state = torch.zeros(self.size) + self.counter
        tensor_dict = tensor_dict.select().set(self.out_key, self._get_out_obs(state))
        tensor_dict.set("done", torch.zeros(*tensor_dict.shape, 1, dtype=torch.bool))
        return tensor_dict

    def _step(
        self,
        tensor_dict: _TensorDict,
    ) -> _TensorDict:
        tensor_dict = tensor_dict.to(self.device)
        a = tensor_dict.get("action")
        assert not self.is_done, "trying to execute step in done env"

        obs = self._obs_step(
            self._get_in_obs(self.current_tensordict.get(self.out_key)), a
        )
        tensor_dict = tensor_dict.select()  # empty tensordict
        tensor_dict.set("next_" + self.out_key, self._get_out_obs(obs))
        done = torch.isclose(obs, torch.ones_like(obs) * (self.counter + 1))
        reward = done.any(-1).unsqueeze(-1)
        done = done.all(-1).unsqueeze(-1)
        tensor_dict.set("reward", reward.to(torch.float))
        tensor_dict.set("done", done)
        return tensor_dict

    def _obs_step(self, obs, a):
        return obs + a / self.maxstep


class DiscreteActionVecPolicy:
    in_keys = ["observation"]
    out_keys = ["action"]

    def _get_in_obs(self, tensor_dict):
        obs = tensor_dict.get(*self.in_keys)
        return obs

    def __call__(self, tensor_dict):
        obs = self._get_in_obs(tensor_dict)
        max_obs = (obs == obs.max(dim=-1, keepdim=True)[0]).cumsum(-1).argmax(-1)
        k = tensor_dict.get(*self.in_keys).shape[-1]
        max_obs = (max_obs + 1) % k
        action = torch.nn.functional.one_hot(max_obs, k)
        tensor_dict.set(*self.out_keys, action)
        return tensor_dict


class DiscreteActionConvMockEnv(DiscreteActionVecMockEnv):
    observation_spec = NdUnboundedContinuousTensorSpec(shape=torch.Size([1, 7, 7]))
    action_spec = OneHotDiscreteTensorSpec(7)
    reward_spec = UnboundedContinuousTensorSpec()
    from_pixels = True

    out_key = "observation_pixels"

    def _get_out_obs(self, obs):
        obs = torch.diag_embed(obs, 0, -2, -1).unsqueeze(0)
        return obs

    def _get_in_obs(self, obs):
        return obs.diagonal(0, -1, -2).squeeze()


class DiscreteActionConvMockEnvNumpy(DiscreteActionConvMockEnv):
    observation_spec = NdUnboundedContinuousTensorSpec(shape=torch.Size([7, 7, 3]))
    from_pixels = True

    def _get_out_obs(self, obs):
        obs = torch.diag_embed(obs, 0, -2, -1).unsqueeze(-1)
        obs = obs.expand(*obs.shape[:-1], 3)
        return obs

    def _get_in_obs(self, obs):
        return obs.diagonal(0, -2, -3)[..., 0]

    def _obs_step(self, obs, a):
        return obs + a.unsqueeze(-1) / self.maxstep


class ContinuousActionConvMockEnv(ContinuousActionVecMockEnv):
    observation_spec = NdUnboundedContinuousTensorSpec(shape=torch.Size([1, 7, 7]))
    action_spec = NdBoundedTensorSpec(-1, 1, (7,))
    reward_spec = UnboundedContinuousTensorSpec()
    from_pixels = True

    out_key = "observation_pixels"

    def _get_out_obs(self, obs):
        obs = torch.diag_embed(obs, 0, -2, -1).unsqueeze(0)
        return obs

    def _get_in_obs(self, obs):
        return obs.diagonal(0, -1, -2).squeeze()


class ContinuousActionConvMockEnvNumpy(ContinuousActionConvMockEnv):
    observation_spec = NdUnboundedContinuousTensorSpec(shape=torch.Size([7, 7, 3]))
    from_pixels = True

    def _get_out_obs(self, obs):
        obs = torch.diag_embed(obs, 0, -2, -1).unsqueeze(-1)
        obs = obs.expand(*obs.shape[:-1], 3)
        return obs

    def _get_in_obs(self, obs):
        return obs.diagonal(0, -2, -3)[..., 0]

    def _obs_step(self, obs, a):
        return obs + a.unsqueeze(-1) / self.maxstep


class DiscreteActionConvPolicy(DiscreteActionVecPolicy):
    in_keys = ["observation_pixels"]
    out_keys = ["action"]

    def _get_in_obs(self, tensor_dict):
        obs = tensor_dict.get(*self.in_keys).diagonal(0, -1, -2).squeeze()
        return obs
