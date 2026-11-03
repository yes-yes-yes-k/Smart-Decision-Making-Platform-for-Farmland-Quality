import torch
import torch.nn as nn

# 定义神经网络模型
class ConstrainedNN(nn.Module):
    def __init__(self, input_size):
        super(ConstrainedNN, self).__init__()
        self.fc1 = nn.Linear(input_size, 128)
        self.fc2 = nn.Linear(128, 64)
        self.fc3 = nn.Linear(64, 16)
        #self.fc4 = nn.Linear(32, 16)
        self.fc5 = nn.Linear(16, 1)
        # 嵌入一元一次线性函数的参数
        self.a = nn.Parameter(torch.randn(1))
        self.b = nn.Parameter(torch.randn(1))

    def forward(self, x, original_x, special_feature_index):
        x = torch.relu(self.fc1(x))
        x = torch.relu(self.fc2(x))
        x = torch.relu(self.fc3(x))
        #x = torch.relu(self.fc4(x))
        x = self.fc5(x)
        # 嵌入一元一次线性函数
        special_feature = original_x[:, special_feature_index].unsqueeze(1)
        x = x + self.a * special_feature + self.b
        return x

# 自定义损失函数
def custom_loss(y_pred, y_true, X, monotonic_feature_index, mean_X_special, mean_y):
    y_true = y_true
    mse_loss = nn.MSELoss()(y_pred, y_true)
    # 惩罚项
    X_special = X[:, monotonic_feature_index]
    punishment = torch.mean((torch.sign(X_special - mean_X_special) - torch.sign(y_pred - mean_y)) ** 2)
    
    # 惩罚项
    # 对于所有样本，计算它们的预测值之间的差值
    # 如果某个样本的特定变量大于另一个样本的特定变量，但预测值却不大于另一个样本的预测值，则增加惩罚
    sorted_indices = torch.argsort(X[:, monotonic_feature_index])  # 按特定变量排序
    sorted_outputs = y_pred[sorted_indices]
    sorted_targets = y_true[sorted_indices]
    
    # 计算相邻样本之间的差值
    output_diff = sorted_outputs[1:] - sorted_outputs[:-1]
    target_diff = sorted_targets[1:] - sorted_targets[:-1]
    
    # 惩罚项：如果输出差值与目标差值的符号不一致，则增加惩罚
    penalty = torch.relu(-output_diff * target_diff).mean()
    
    return mse_loss + 2*punishment + penalty # 权衡 mse_loss 和惩罚项的权重