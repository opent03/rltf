import json
import logging
import os
import time
import numpy as np

from gym        import error
from gym.utils  import atomic_write

from rltf.utils import rltf_log
import rltf.conf

logger        = logging.getLogger(__name__)
stats_logger  = logging.getLogger(rltf.conf.STATS_LOGGER_NAME)


class StatsRecorder:

  def __init__(self, log_dir, mode='t', n_ep_stats=100):
    """
    Args:
      log_dir: str. The path for the directory where the videos are saved
      n_ep_stats: int. Number of episodes over which to report the runtime statistitcs
    """

    # Member data
    self.log_dir    = log_dir
    self.n_ep_stats = n_ep_stats
    self.log_info   = None
    self.steps_p_s  = None
    self.t_last_log     = time.time()   # Time at which the last runtime log happened
    self.step_last_log  = 0             # Step at which the last runtime log happened

    # Training statistics
    self.train_ep_rews = []
    self.train_ep_lens = []
    self.train_steps   = 0      # Total number of environment steps in train mode
    self.train_stats   = None   # A dictionary with runtime statistics about training

    # Evaluation statistics
    self.eval_ep_rews = []
    self.eval_ep_lens = []
    self.eval_steps   = 0       # Total number of environment steps in eval mode
    self.eval_stats   = None    # A dictionary with runtime statistics about evaluation

    # Runtime variables
    self.ep_reward  = None
    self.ep_steps   = None
    self.env_steps  = 0         # Total number of environment steps in any mode
    self.disabled   = False
    self._mode      = mode      # Running mode: either 't' (train) or 'e' (eval)

    if not os.path.exists(self.log_dir):
      logger.info('Creating stats directory %s', self.log_dir)
      os.makedirs(self.log_dir, exist_ok=True)


  @property
  def mode(self):
    return self._mode


  @mode.setter
  def mode(self, mode):
    if mode not in ['t', 'e']:
      raise error.Error('Invalid mode {}: must be t for training or e for evaluation', mode)
    self._mode = mode


  def before_step(self, action):
    assert not self.disabled


  def after_step(self, obs, reward, done, info):
    self.ep_steps   += 1
    self.env_steps  += 1
    self.ep_reward  += reward

    if done:
      self._finish_episode()


  def _finish_episode(self):
    # If the user changes the mode in the middle of the episode,
    # the mode at the end of the episode is used
    if self._mode == 't':
      self.train_steps += self.ep_steps
      self.train_ep_lens.append(np.int32(self.ep_steps))
      self.train_ep_rews.append(np.float32(self.ep_reward))
    else:
      self.eval_steps += self.ep_steps
      self.eval_ep_lens.append(np.int32(self.ep_steps))
      self.eval_ep_rews.append(np.float32(self.ep_reward))


  def before_reset(self):
    assert not self.disabled


  def after_reset(self, obs):
    self.ep_steps   = 0
    self.ep_reward  = 0


  def close(self):
    self.disabled = True


  def define_log_info(self, custom_log_info):
    """Build a list of tuples `(name, modifier, lambda)`. This list is
    used to print the runtime statistics logs. The tuple is defined as:
      `name`: `str`, the name of the reported value
      `modifier`: `str`, the type modifier for printing the value, e.g. `d` for int
      `lambda`: A function that takes the current **agent** timestep as argument
        and returns the value to be printed.
    Args:
      custom_log_info: `list`. Must have the same structure as the above list. Allows
        for logging custom data coming from the agent
    """

    self.train_stats = {
      "mean_ep_rew":    float("nan"),
      "mean_ep_len":    float("nan"),
      "best_mean_rew":  -float("inf"),
      "best_ep_rew":    -float("inf"),
      "ep_last_stats":  0,
    }

    self.eval_stats = {
      "mean_ep_rew":    float("nan"),
      "mean_ep_len":    float("nan"),
      "best_mean_rew":  -float("inf"),
      "best_ep_rew":    -float("inf"),
      "ep_last_stats":  0,
    }

    n = self.n_ep_stats

    default_info = [
      ("train/agent_steps",                     "d",    lambda t: t),
      ("train/mean_steps_per_sec",              ".3f",  lambda t: self.steps_p_s),

      ("train/env_steps",                       "d",    lambda t: self.train_steps),
      ("train/episodes",                        "d",    lambda t: len(self.train_ep_rews)),
      ("train/mean_ep_len (%d eps)"%n,          ".3f",  lambda t: self.train_stats["mean_ep_len"]),
      ("train/mean_ep_reward (%d eps)"%n,       ".3f",  lambda t: self.train_stats["mean_ep_rew"]),
      ("train/best_mean_ep_rew (%d eps)"%n,     ".3f",  lambda t: self.train_stats["best_mean_rew"]),
      ("train/best_episode_rew",                ".3f",  lambda t: self.train_stats["best_ep_rew"]),

      ("eval/env_steps",                        "d",    lambda t: self.eval_steps),
      ("eval/episodes",                         "d",    lambda t: len(self.eval_ep_rews)),
      ("eval/mean_ep_len (%d eps)"%n,           ".3f",  lambda t: self.eval_stats["mean_ep_len"]),
      ("eval/mean_ep_reward (%d eps)"%n,        ".3f",  lambda t: self.eval_stats["mean_ep_rew"]),
      ("eval/best_mean_ep_rew (%d eps)"%n,      ".3f",  lambda t: self.eval_stats["best_mean_rew"]),
      ("eval/best_episode_rew",                 ".3f",  lambda t: self.eval_stats["best_ep_rew"]),

      # ("mean/n_eps > 0.8*best_rew (%d eps)"%n,  ".3f",  self._stats_frac_good_episodes),
    ]

    log_info = default_info + custom_log_info
    self.log_info = rltf_log.format_tabular(log_info)


  def _stats_mean(self, data):
    if len(data) > 0:
      return np.mean(data[-self.n_ep_stats:])
    return float("nan")


  def _compute_runtime_stats(self, step):
    """Update the values of the runtime statistics variables"""

    def _stats_max(data, i=0):
      if len(data[i:]) > 0:
        return np.max(data[i:])
      return -float("inf")

    self.train_stats["mean_ep_rew"] = self._stats_mean(self.train_ep_rews)
    self.train_stats["mean_ep_len"] = self._stats_mean(self.train_ep_lens)
    self.train_stats["best_mean_rew"] = max(self.train_stats["best_mean_rew"],
                                            self.train_stats["mean_ep_rew"])
    best_ep_rew = _stats_max(self.train_ep_rews, self.train_stats["ep_last_stats"])
    self.train_stats["best_ep_rew"] = max(self.train_stats["best_ep_rew"], best_ep_rew)
    self.train_stats["ep_last_stats"] = len(self.train_ep_rews)


    self.eval_stats["mean_ep_rew"] = self._stats_mean(self.eval_ep_rews)
    self.eval_stats["mean_ep_len"] = self._stats_mean(self.eval_ep_lens)
    self.eval_stats["best_mean_rew"] = max(self.eval_stats["best_mean_rew"],
                                           self.eval_stats["mean_ep_rew"])
    best_ep_rew = _stats_max(self.eval_ep_rews, self.eval_stats["ep_last_stats"])
    self.eval_stats["best_ep_rew"] = max(self.eval_stats["best_ep_rew"], best_ep_rew)
    self.eval_stats["ep_last_stats"] = len(self.eval_ep_rews)

    t_now  = time.time()
    if self._mode == 't':
      steps_per_s = (step - self.step_last_log) / (t_now - self.t_last_log)
      steps_per_s = steps_per_s if self.steps_p_s is None else (steps_per_s + self.steps_p_s) / 2.0
      self.steps_p_s = steps_per_s
      self.step_last_log = step
    self.t_last_log = t_now


  def get_mean_ep_rew(self):
    return self._stats_mean(self.train_ep_rews)


  def log_stats(self, t):
    """Log the training progress
    Args:
      t: int. Current **agent** timestep
    """

    # Update the statistics
    self._compute_runtime_stats(t)

    stats_logger.info("")
    for s, lambda_v in self.log_info:
      stats_logger.info(s.format(lambda_v(t)))
    stats_logger.info("")


  def save(self):
    """Save the statistics data to disk. Must be manually called"""
    if self.disabled:
      return

    summary_file = os.path.join(self.log_dir, "stats_summary.json")
    data = {
      "total_env_steps":  self.env_steps,
      "train_steps":      self.train_steps,
      "train_episodes":   len(self.train_ep_rews),
      "eval_steps":       self.eval_steps,
      "eval_episodes":    len(self.eval_ep_rews),
      "steps_per_s":      self.steps_p_s,
    }

    with atomic_write.atomic_write(summary_file) as f:
      json.dump(data, f, indent=4, sort_keys=True)

    if self.train_ep_rews:
      train_rew_file = os.path.join(self.log_dir, "train_ep_rews.npy")
      with atomic_write.atomic_write(train_rew_file, True) as f:
        np.save(f, np.asarray(self.train_ep_rews, dtype=np.float32))

    if self.eval_ep_rews:
      eval_rew_file = os.path.join(self.log_dir, "eval_ep_rews.npy")
      with atomic_write.atomic_write(eval_rew_file, True) as f:
        np.save(f, np.asarray(self.eval_ep_rews, dtype=np.float32))