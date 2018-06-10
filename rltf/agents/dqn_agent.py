import gym
import numpy as np
import tensorflow as tf

from rltf.agents.off_pi import ParallelOffPolicyAgent
from rltf.agents.off_pi import SequentialOffPolicyAgent
from rltf.memory        import ReplayBuffer


class AgentDQN(ParallelOffPolicyAgent):

  def __init__(self,
               model,
               model_kwargs,
               opt_conf,
               exploration,
               update_target_freq=10000,
               memory_size=int(1e6),
               obs_len=4,
               epsilon_eval=0.001,
               **agent_kwargs
              ):
    """
    Args:
      model: rltf.models.Model. TF implementation of a model network
      model_kwargs: dict. Model-specific keyword arguments to pass to the model
      opt_conf: rltf.optimizers.OptimizerConf. Config for the network optimizer
      exploration: rltf.schedules.Schedule. Epsilon value for e-greedy exploration
      update_target_freq: Period in number of agent steps at which to update the target net
      memory_size: int. Size of the replay buffer
      obs_len: int. How many environment observations comprise a single state.
      agent_kwargs: Keyword arguments that will be passed to the Agent base class
    """

    super().__init__(**agent_kwargs)

    assert isinstance(self.env_train.observation_space, gym.spaces.Box)
    assert isinstance(self.env_train.action_space,      gym.spaces.Discrete)

    self.opt_conf = opt_conf
    self.exploration = exploration
    self.epsilon_eval = epsilon_eval
    self.update_target_freq = update_target_freq

    # Get environment specs
    n_actions = self.env_train.action_space.n
    obs_shape = self.env_train.observation_space.shape
    obs_shape = list(obs_shape)
    obs_len   = obs_len if len(obs_shape) == 3 else 1

    model_kwargs["obs_shape"] = obs_shape
    model_kwargs["n_actions"] = n_actions
    model_kwargs["opt_conf"]  = opt_conf

    self.model      = model(**model_kwargs)
    self.replay_buf = ReplayBuffer(memory_size, obs_shape, np.uint8, [], np.uint8, obs_len)

    # Configure what information to log
    self._define_log_info()

    # Custom TF Tensors and Ops
    self.learn_rate_ph  = None


  def _build(self):
    # Create Learning rate placeholders
    self.learn_rate_ph  = tf.placeholder(tf.float32, shape=(), name="learn_rate_ph")

    # Set the learn rate placeholders for the model
    self.opt_conf.lr_ph = self.learn_rate_ph

    # Add summaries
    tf.summary.scalar("train/learn_rate", self.learn_rate_ph)


  def _append_log_info(self):
    log_info = [
      ( "train/learn_rate", "f", self.opt_conf.lr_value ),
      ( "train/epsilon",    "f", self.exploration.value ),
    ]
    return log_info


  def _append_summary(self, summary, t):
    summary.value.add(tag="train/epsilon", simple_value=self.exploration.value(t))


  def _get_feed_dict(self, batch, t):
    feed_dict = {
      self.model.obs_t_ph:       batch["obs"],
      self.model.act_t_ph:       batch["act"],
      self.model.rew_t_ph:       batch["rew"],
      self.model.obs_tp1_ph:     batch["obs_tp1"],
      self.model.done_ph:        batch["done"],
      self.learn_rate_ph:        self.opt_conf.lr_value(t),
    }

    return feed_dict


  def _action_train(self, state, t):
    # Run epsilon greedy policy
    epsilon = self.exploration.value(t)
    if self.prng.uniform(0,1) < epsilon:
      action = self.env_train.action_space.sample()
    else:
      # Run the network to select an action
      action = self.model.action_train(self.sess, state)
    return action


  def _action_eval(self, state, t):
    # Run epsilon greedy policy
    if self.prng.uniform(0,1) < self.epsilon_eval:
      action = self.env_eval.action_space.sample()
    else:
      # Run the network to select an action
      action = self.model.action_eval(self.sess, state)
    return action


  def _reset(self):
    pass
