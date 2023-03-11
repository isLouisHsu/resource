import os
import gym
import numpy as np
from copy import deepcopy
from itertools import chain
from collections import deque

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical

env = gym.make('CartPole-v1')
env = env.unwrapped
state_number = env.observation_space.shape[0]
action_number = env.action_space.n
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

class Actor(nn.Module):

    def __init__(self):
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(state_number, 32),
            nn.ReLU(inplace=True),
            nn.Linear(32, 32),
            nn.ReLU(inplace=True),
            nn.Linear(32, action_number),
            nn.Softmax(dim=-1),
        )

    def forward(self, state):
        pi = self.layers(state)  # (batch_size, action_number)
        return pi

class Critic(nn.Module):

    def __init__(self):
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(state_number, 32),
            nn.ReLU(inplace=True),
            nn.Linear(32, 32),
            nn.ReLU(inplace=True),
            nn.Linear(32, 1),
        )

    def forward(self, state):
        value = self.layers(state).squeeze(-1)  # (batch_size,)
        return value

class ActorCritic():

    def __init__(
        self,
        gamma=0.99,
        update_steps=1,
        lr=5e-4,
        weight_decay=0.0,
    ):
        self.gamma = gamma
        self.update_steps = update_steps

        self.buffer = []
        self.actor = Actor().to(device)
        self.critic = Critic().to(device)
        self.optimizer = torch.optim.Adam(
            chain(self.actor.parameters(), self.critic.parameters()), 
            lr=lr, weight_decay=weight_decay
        )
        self.loss_fct = nn.SmoothL1Loss()
    
    @torch.no_grad()
    def choose_action(self, state):
        state = torch.from_numpy(state).float().unsqueeze(0).to(device)
        pi = self.actor(state)
        dist = torch.distributions.Categorical(pi)
        action = dist.sample().item()
        return action
    
    @torch.no_grad()
    def get_value(self, state):
        state = torch.from_numpy(state).float().unsqueeze(0).to(device)
        value = self.critic(state)
        return value

    def store_experience(self, experience):
        self.buffer.append(experience)
    
    def update(self):
        # 得到数据
        get_tensor = lambda x: torch.tensor([b[x] for b in self.buffer]).to(device)
        states = get_tensor(0).float()
        actions = get_tensor(1).long()
        rewards = get_tensor(2).float()
        next_states = get_tensor(3).float()
        done = get_tensor(4).long()

        # # 改进2：为每步t赋予不同权重
        # for t in reversed(range(0, rewards.size(0) - 1)):
        #     rewards[t] = rewards[t] + self.gamma * rewards[t + 1]
        # 改进1：增加一个奖励基准$b$，这里用均值；另归一化，有助于收敛
        rewards = (rewards - rewards.mean()) / rewards.std()

        # 计算target
        with torch.no_grad():
            # 同DQN，计算Q函数
            max_next_q = self.critic(next_states).max(dim=-1)[0]
            target_q = rewards + self.gamma * max_next_q

        for i in range(self.update_steps):
            # 计算损失
            pi = self.actor(states)
            q = self.critic(states)

            action_log_probs = torch.sum(pi.log() * F.one_hot(actions), dim=1)
            loss_actor = - (action_log_probs * q).mean()    # 基于TD误差
            loss_critic = self.loss_fct(q, target_q)

            loss = loss_actor + loss_critic
            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()

        # 清除缓存
        del self.buffer[:]

        return loss.item()

def train(agent, num_episodes=5000, render=False):
    step = 0
    for i in range(num_episodes):
        total_rewards = 0
        done = False
        state, _ = env.reset()
        while not done:
            step += 1
            if render: env.render()
            # 选择动作
            action = agent.choose_action(state)
            # 与环境产生交互
            next_state, reward, done, truncated, info = env.step(action)
            # 预处理，修改reward，你也可以不修改奖励，直接用reward，都能收敛
            x, x_dot, theta, theta_dot = next_state
            r1 = (env.x_threshold - abs(x)) / env.x_threshold - 0.8
            r2 = (env.theta_threshold_radians - abs(theta)) / env.theta_threshold_radians - 0.5
            r3 = 3 * r1 + r2
            # 经验缓存
            agent.store_experience((state, action, r3, next_state, done))
            # 更新状态
            state = next_state
            total_rewards += reward
        
        # 回合结束，更新参数
        loss = agent.update()
        if i % 50 == 0:
            print('episode:{} reward:{}'.format(i, total_rewards))

def test(agent, num_episodes=10, render=False):
    env = gym.make('CartPole-v1', render_mode="human" if render else None)
    step = 0
    eval_rewards = []
    for i in range(num_episodes):
        total_rewards = 0
        done = False
        state, _ = env.reset()
        while not done:
            step += 1
            if render: env.render()
            # 选择动作
            action = agent.choose_action(state)
            # 与环境产生交互
            next_state, reward, done, truncated, info = env.step(action)
            # 更新状态
            state = next_state
            total_rewards += reward
        eval_rewards.append(total_rewards)
    return sum(eval_rewards) / len(eval_rewards)

if __name__ == "__main__":
    agent = ActorCritic()
    train(agent, render=False)
    test(agent, render=True)
