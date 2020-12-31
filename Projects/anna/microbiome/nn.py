from load_merge_otu_mf import OtuMfHandler
from Preprocess import preprocess_data
from pca import *
from plot_confusion_matrix import *
import pandas as pd
import math
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
import torch
import torchvision
import torchvision.transforms as transforms
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torchvision import datasets, transforms
import numpy as np
from torch.utils.data.sampler import SubsetRandomSampler
from preprocess_and_distance_PSC import psc

# otu = 'C:/Users/Anna/Desktop/docs/otu_psc2.csv'
# mapping = 'C:/Users/Anna/Desktop/docs/mapping_psc.csv'
# OtuMf = OtuMfHandler(otu, mapping, from_QIIME=False)
# preproccessed_data = preprocess_data(OtuMf.otu_file, visualize_data=False, taxnomy_level=7)
#
# otu_after_pca, _ = apply_pca(preproccessed_data, n_components=17)
# merged_data = otu_after_pca.join(OtuMf.mapping_file['DiagnosisGroup'])
#
# merged_data.fillna(0)
#
# mapping_disease_for_labels = {'Control':0,'Cirrhosis/HCC':1, 'PSC/PSC+IBD':2}
# mapping_disease = {'Control':0,'Cirrhosis ':1, 'HCC':1, 'PSC+IBD':2,'PSC':2}
# merged_data['DiagnosisGroup'] = merged_data['DiagnosisGroup'].map(mapping_disease)
# merged_data = merged_data.join(OtuMf.mapping_file[['Age', 'BMI', 'FattyLiver','RegularExercise', 'Smoking']])
# mappin_boolean = {'yes' :1, 'no': 0, 'Control': 0, '0':0, '1':1}
# merged_data['FattyLiver'] = merged_data['FattyLiver'].map(mappin_boolean)
# merged_data['RegularExercise'] = merged_data['RegularExercise'].map(mappin_boolean)
# merged_data['Smoking'] = merged_data['Smoking'].map(mappin_boolean)

#
df, mapping_file = psc(perform_distance=False,level =3)
otu_after_pca, _ = apply_pca(df, n_components=24)
merged_data = df.join(mapping_file)

X,y = merged_data.loc[:, merged_data.columns != 'DiagnosisGroup'], merged_data['DiagnosisGroup']

train_target = torch.tensor(y.values.astype(np.float32))
train = torch.tensor(X.values.astype(np.float32))
train_tensor = torch.utils.data.TensorDataset(train, train_target) #, shuffle=True)

num_train = len(X)
indices = list(range(num_train))
train_idx,validation_idx = train_test_split(indices,test_size=0.2, random_state=42)

#validation_idx = np.random.choice(indices, size=split, replace=False)
#train_idx = list(set(indices) - set(validation_idx))
print(validation_idx)
train_sampler = SubsetRandomSampler(train_idx)
validation_sampler = SubsetRandomSampler(validation_idx)

size = X.shape[1]
#train_loader = torch.utils.data.DataLoader(dataset = train_tensor, batch_size =8,  sampler=train_sampler)
#validation_loader = torch.utils.data.DataLoader(dataset = train_tensor, batch_size =8,  sampler=validation_sampler)
#test_target = torch.tensor(y_test.values.astype(np.float32))
#test = torch.tensor(X_test.values.astype(np.float32))
#test_tensor = torch.utils.data.TensorDataset(test, test_target)
#test_loader = torch.utils.data.DataLoader(dataset = test_tensor, batch_size = 8, shuffle = True)

# print (num_train)
# print (len(validation_idx))
# print (len(train_idx))
# print(len(train_loader))
# print(len(validation_loader))

class NNet(nn.Module):
    def __init__(self,size, dropout):
        super(NNet, self).__init__()
        n_features = size
        n_out = 3

        self.hidden0 = nn.Sequential(
            nn.Linear(n_features, 60),
            #nn.BatchNorm1d(60, eps=1e-04, momentum=0.1),
            nn.LeakyReLU(0.2),
            nn.Dropout(dropout)
        )
        self.hidden1 = nn.Sequential(
            nn.Linear(60, 10),
            #nn.BatchNorm1d(30, eps=1e-04, momentum=0.1),
            nn.LeakyReLU(0.2),
            nn.Dropout(dropout)
        )
        self.out = nn.Sequential(
            nn.Linear(10, n_out)
        )

    def forward(self, x):
        x = self.hidden0(x)
        x = self.hidden1(x)
       # x = self.hidden2(x)
        x = self.out(x)
        return F.log_softmax(x, dim=1)


#print(model)

def train(epoch, model,optimizer):
    model.train()
    t_loss = 0
    correct = 0
    train_loader = torch.utils.data.DataLoader(dataset=train_tensor, batch_size=32, sampler=train_sampler)
    #validation_loader = torch.utils.data.DataLoader(dataset=train_tensor, batch_size=8, sampler=validation_sampler)
    for batch_idx, (data, labels) in enumerate(train_loader):
        optimizer.zero_grad()
        output = model(data)
        labels = labels.long()
        loss = F.nll_loss(output, labels)
        loss.backward()
        optimizer.step()
        pred = output.data.max(1, keepdim=True)[1]  # get the index of the max log-probability
        correct += pred.eq(labels.data.view_as(pred)).cpu().sum()
        #if batch_idx % 2 == 0:
        # print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
        #         epoch, batch_idx * len(data), len(train_sampler),
        #                100. * batch_idx / len(train_sampler), loss.item()))
        t_loss += loss.item()
    t_loss /= len(train_loader)
    #print('Train Epoch: {} \tLoss: {:.6f}'.format(epoch,t_loss))
    return t_loss, 100. * correct / len(train_sampler)

def validation(model):
    model.eval()
   # for name, param in model.named_parameters():
    #        print(name, param.data)
    val_loss = 0
    correct = 0
    validation_loader = torch.utils.data.DataLoader(dataset=train_tensor, batch_size=32, sampler=validation_sampler)
    for data, target in validation_loader:
        #print(data)
        output = model(data)
        target = target.long()
        #validation_loss += F.nll_loss(output, target, size_average=False).item()
        val_loss += F.nll_loss(output, target).item() # sum up batch loss
        pred = output.data.max(1, keepdim=True)[1] # get the index of the max log-probability
        correct += pred.eq(target.data.view_as(pred)).cpu().sum()
    val_loss /= len(validation_loader)
    #print('\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
     #   val_loss, correct, len(validation_sampler),
      #  100. * correct / len(validation_sampler)))
    return val_loss, 100. * correct / len(validation_sampler)



def train_and_eval(size, lr, weight_decay,dropout=0.35):
    #optimizer = optim.Adam(model.parameters(), lr=0.0005, weight_decay=0.001)
    model = NNet(size,dropout)
    optimizer = optim.SGD(model.parameters(), lr=lr, weight_decay=weight_decay)
    epochs = []
    train_loss = []
    control_loss = []
    #train_accuracy = []
    test_accuracy = []
    prediction =[]
    data = []
    for epoch in range(1, 1000):
    #for data, label in validation_loader.dataset:
    #    print(label.data)
        epochs.append(epoch)
        t_l,_ =train(epoch,model, optimizer)
        train_loss.append(t_l)
        #train_accuracy.append(t_a)
        v_l,v_a =validation(model)
        # if v_a == 85:
        #     for data,target in train_tensor:
        #         #print(data)
        #         output = model(data)
        #         pred = output.data.max(1, keepdim=True)[1]
        #         prediction.append(pred)
        #         data.append(data)
        test_accuracy.append(v_a)
        control_loss.append(v_l)

#print('train loss ' + str(sum(train_loss) / float(len(train_loss))))
#print('test loss ' + str(sum(control_loss) / float(len(control_loss))))
    m_t_a = max(test_accuracy)
    print('LR : {}, WD : {}, Dropout : {:.3f} test accuracy : {} '.format(lr, weight_decay, dropout,m_t_a))

# plot graphs
    x2,y2 = zip(*(zip(epochs,control_loss)))
    x3,y3 = zip(*(zip(epochs,train_loss)))
    font = {'size': 10}
    plt.rc('font', **font)
    plt.plot(x2,y2,lw=2, color='blue', label='Validation')
    plt.plot(x3,y3,lw=2, color='red', label='Train')
    plt.legend( loc=1,ncol=1)
    plt.title('LpE:lr- %s,weight_decay - %s, dropout - %s, acc - %s ' %(lr, weight_decay,dropout, m_t_a.item()))
    plt.xlim(0, 1000)
    #plt.ylim(0, 2)
    plt.show()

for lr in range (30, 0,-5):
    for wd in range(10,0,-1):
        for do in range(20,50,5):
            train_and_eval(size, lr/10000, wd/1000, do/100)


#train_and_eval(size, 0.001, 0.008, 0.35)