#coding:UTF-8

import numpy as np
from BirdModel import BirdModel
from BirdAgent import BirdAgent
from replay_memory import ReplayMemory, Experience
from parl.algorithms import DQN
from tqdm import tqdm
from utils import resizeBirdrToAtari
import time
from collections import deque
from game.BirdEnv import BirdEnv
from parl.utils import logger
import matplotlib.pyplot as plt
import os
import sys
sys.path.append("game/")

#=========可调节的超参数 start=========

#图像输入大小(修改后，网络模型的height、weight也必须修改)
IMAGE_SIZE = (84, 84)

#记录最近4帧(修改后，网络模型的通道数也必须修改)
CONTEXT_LEN = 4

#replay-memory的大小
MEMORY_SIZE = int(8e4)

#充满replay-memory,使其达到warm-up-size才开始训练
MEMORY_WARMUP_SIZE = MEMORY_SIZE//20

#默认不跳帧
FRAME_SKIP = None

#网络学习频率
UPDATE_FREQ = 2

#衰减因子
GAMMA = 0.99

#学习率
LEARNING_RATE = 1e-3 * 0.5

#一共走多少步
TOTAL=1e6

#batch-size
batchSize=32

#每多少个episode测试一次
eval_freq=100

#一轮episode最多执行多少次step，不然小鸟会无限制的飞下去,相当于gym.env中的_max_episode_steps属性
MAX_Step_Limit=int(1<<12)

#阈值，当测试reward的最小值超过threshold_min、平均值超过threshold_avg后就停止训练，防止网络过拟合
threshold_min=256
threshold_avg=400

#=========可调节的超参数 end=========

#以下为非重要参数
#记录日志的频率
log_freq=10
#初始化平均奖励
meanReward=0
#记录训练的episode
trainEpisode=0
#学习曲线数组
learning_curve=[]
#初始平均奖励超过eval_mean_save才保存模型
eval_mean_save=32

#训练一个episode
def run_train_episode(env, agent, rpm):
    global trainEpisode
    global meanReward
    total_reward = 0
    all_cost = []
    #重置环境
    state,_, __ = env.reset()
    step = 0
    #循环每一步
    while True:
        context = rpm.recent_state()
        context.append(resizeBirdrToAtari(state))
        context = np.stack(context, axis=0)
        #用ε-greedy的方式选一个动作
        action = agent.sample(context)
        #执行动作
        next_state, reward, isOver,_ = env.step(action)
        step += 1
        #存入replay_buffer
        rpm.append(Experience(resizeBirdrToAtari(state), action, reward, isOver))
        if rpm.size() > MEMORY_WARMUP_SIZE:
            if step % UPDATE_FREQ == 0:
                #从replay_buffer中随机采样
                batch_all_state, batch_action, batch_reward, batch_isOver = rpm.sample_batch(
                    batchSize)
                batch_state = batch_all_state[:, :CONTEXT_LEN, :, :]
                batch_next_state = batch_all_state[:, 1:, :, :]
                #执行SGD,训练参数θ
                cost = agent.learn(batch_state, batch_action, batch_reward,
                                   batch_next_state, batch_isOver)
                all_cost.append(float(cost))
        total_reward += reward
        state = next_state
        if isOver or step>=MAX_Step_Limit:
            break
    if all_cost:
        trainEpisode+=1
        #以滑动平均的方式打印平均奖励
        meanReward=meanReward+(total_reward-meanReward)/trainEpisode
        print('\n trainEpisode:{},total_reward:{:.2f}, meanReward:{:.2f} mean_cost:{:.3f}'\
              .format(trainEpisode,total_reward, meanReward,np.mean(all_cost)))
    return total_reward, step

def run_evaluate_episode(env, agent,rpm):
    state, _, __ = env.reset('test')
    total_reward = 0
    step=0
    while True:
        context = rpm.recent_state()
        context.append(resizeBirdrToAtari(state))
        context = np.stack(context, axis=0)
        action = agent.predict(context)
        next_state, reward, isOver,_ = env.step(action)
        step+=1
        rpm.appendForTest(Experience(resizeBirdrToAtari(state), action, reward, isOver))
        total_reward += reward
        state=next_state
        if isOver or step>=MAX_Step_Limit:
            time.sleep(2)
            break
    return total_reward

#保存模型参数
def save(agent):
    learnDir = os.path.join(logger.get_dir(),'learn')
    predictDir = os.path.join(logger.get_dir(),'predict')
    agent.save_params(learnDir,predictDir)

#恢复模型
def restore(agent):
    print(logger.get_dir())
    learnDir = r"D:\GoogleDownloads\zheng_bo_pu-PARL-Sample-master\PARL-Sample\flappy_bird\log_dir\Train_Test_Working_Flow\learn"
    predictDir = r"D:\GoogleDownloads\zheng_bo_pu-PARL-Sample-master\PARL-Sample\flappy_bird\log_dir\Train_Test_Working_Flow\predict"
    print('restore model from {}'.format(learnDir))
    agent.load_params(learnDir,predictDir)

#初始化 环境-environment、模型-model、算法-algorithm、智能体-agent
def init_environment():
    env = BirdEnv()
    action_dim = 2
    hyperparas = {
        'action_dim': action_dim,
        'gamma': GAMMA,
        'lr': LEARNING_RATE
    }
    model = BirdModel(action_dim)
    algorithm = DQN(model, action_dim, GAMMA, LEARNING_RATE)
    agent = BirdAgent(algorithm, action_dim)
    return env,agent

#训练
def train():
    env,agent=init_environment()
    rpm = ReplayMemory(MEMORY_SIZE, IMAGE_SIZE, CONTEXT_LEN)
    rpmForTest = ReplayMemory(128, IMAGE_SIZE, CONTEXT_LEN)
    # with tqdm(total=MEMORY_WARMUP_SIZE) as pbar:
    while rpm.size() < MEMORY_WARMUP_SIZE:
        ep_reward, step = run_train_episode(env, agent, rpm)
            # pbar.update(step)

    # train
    print('TrainStart!')
    # pbar = tqdm(total=TOTAL)
    #用一个双端队列记录最近16次episode的平均值
    avgQueue=deque(maxlen=16)
    total_step = 0
    max_reward = 0
    global learning_curve 
    while True:
        ep_reward, step = run_train_episode(env, agent, rpm)
        total_step += step
        avgQueue.append(ep_reward)
        if ep_reward>max_reward:
            max_reward=ep_reward
        # pbar.set_description('exploration:{:.4f},max_reward:{:.2f}'.format(agent.exploration,max_reward))
        # pbar.update(step)
        if trainEpisode%log_freq==0:
            learning_curve.append(np.mean(avgQueue))
        if trainEpisode%eval_freq==0:
            global eval_mean_save
            eval_rewards=[]
            for _ in range(16):
                eval_reward = run_evaluate_episode(env, agent, rpmForTest)
                eval_rewards.append(eval_reward)
                print('TestReward:{:.2f}'.format(eval_reward))
            print('TestMeanReward:{:.2f}'.format(np.mean(eval_rewards)))
            if np.mean(eval_rewards)>eval_mean_save:
                eval_mean_save=np.mean(eval_rewards)
                save(agent)
                print('ModelSaved!')
            if np.min(eval_rewards) >= threshold_min and np.mean(eval_rewards) >= threshold_avg:
                print("########## Solved with {} episode!###########".format(trainEpisode))
                save(agent)
                break
        if total_step >= TOTAL:
            break
    # pbar.close()
    
    #绘制学习曲线
    X=np.arange(0,len(learning_curve))
    X*=log_freq
    plt.title('LearningCurve')
    plt.xlabel('TrainEpisode')
    plt.ylabel('AvgReward')
    plt.plot(X,learning_curve)
    plt.show()

#测试
def test():
    env,agent=init_environment()
    rpmForTest=ReplayMemory(128, IMAGE_SIZE, CONTEXT_LEN)
    restore(agent) 
    pbar = tqdm(total=TOTAL)
    pbar.write("testing:")
    eval_rewards = []
    for _ in tqdm(range(64), desc='eval agent'):
        eval_reward = run_evaluate_episode(env, agent, rpmForTest)
        eval_rewards.append(eval_reward)
        print('TestReward:{:.2f}'.format(eval_reward))
    print("eval_mean_reward:{:.2f},eval_min_reward:{:.2f}".format(np.mean(eval_rewards),np.min(eval_rewards)))
    pbar.close()
    
if __name__ == '__main__':
    print("train or test ?")
    mode=input()
    print(mode)
    if mode=='train':
        train()
    elif mode=='test':
        test()
    else:
        print('Invalid input!')
