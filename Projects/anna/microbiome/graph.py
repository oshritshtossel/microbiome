import networkx as nx
from load_merge_otu_mf import OtuMfHandler
from Preprocess import preprocess_data
from pca import *
import scipy
from plot_confusion_matrix import *
import pandas as pd
import math
import matplotlib.pyplot as plt
import numpy as np
from torch.utils.data.sampler import SubsetRandomSampler
from sklearn import metrics
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split, RepeatedStratifiedKFold,LeaveOneOut
import re

otu = 'C:/Users/Anna/Desktop/docs/otu_psc2.csv'
mapping = 'C:/Users/Anna/Desktop/docs/mapping_psc.csv'
OtuMf = OtuMfHandler(otu, mapping, from_QIIME=False)
preproccessed_data = preprocess_data(OtuMf.otu_file, visualize_data=False, taxnomy_level=6)
#visualize_pca(preproccessed_data)

otu_after_pca, _ = apply_pca(preproccessed_data, n_components=30)
merged_data = otu_after_pca.join(OtuMf.mapping_file['DiagnosisGroup'])

merged_data.fillna(0)

mapping_disease_for_labels = {'Control':0,'Cirrhosis/HCC':1, 'PSC/PSC+IBD':2}
mapping_disease = {'Control':0,'Cirrhosis ':1, 'HCC':1, 'PSC+IBD':2,'PSC':2}
merged_data['DiagnosisGroup'] = merged_data['DiagnosisGroup'].map(mapping_disease)
merged_data = merged_data.join(OtuMf.mapping_file[['Age', 'BMI', 'FattyLiver','RegularExercise', 'Smoking']])
mappin_boolean = {'yes' :1, 'no': 0, 'Control': 0, '0':0, '1':1}
merged_data['FattyLiver'] = merged_data['FattyLiver'].map(mappin_boolean)
merged_data['RegularExercise'] = merged_data['RegularExercise'].map(mappin_boolean)
merged_data['Smoking'] = merged_data['Smoking'].map(mappin_boolean)

X = merged_data.loc[:, merged_data.columns != 'DiagnosisGroup']
y = merged_data['DiagnosisGroup']

loo = LeaveOneOut()

for md in range(4,5):
      for ne in range (150,200,50):
           for lr in range (15, 20, 5):
               accuracy = []
# # #             auc_train = []
# # #             auc = []
               #for i in range(0,40,2):
               #        X_train, X_test, y_train, y_test = train_test_split(
               #            merged_data.loc[:, merged_data.columns != 'DiagnosisGroup'], merged_data['DiagnosisGroup'],
               #            test_size=0.25, random_state=i)
               y_pred_list = []
               x_indx = []
               for train_index, test_index in loo.split(X):
                    train_index=list(train_index)
                    #print("%s %s" % (train_index, test_index))
                    X_train, X_test = X.iloc[train_index,:], X.iloc[test_index,:]
                    y_train, y_test = y[train_index], y[test_index]
                    model = XGBClassifier(max_depth=md,n_estimators = ne ,learning_rate = lr/100,  objective='multi:softmax' )
# # #                                           #objective= 'binary:logistic')
                    model.fit(X_train, y_train)
                    x_indx.append(X_test.index[0])
                    y_pred = model.predict(X_test)
# # #                     #pred_train = model.predict_proba(X_train)[:, 1]
# # #                     #auc_train.append(metrics.roc_auc_score(y_train, pred_train))
# # #                     #y_pred = model.predict_proba(X_test)[:,1]
# # #                     #try:
# # #                     #    auc.append(metrics.roc_auc_score(y_test, y_pred))
# # #                     #except:
# # #                     #    continue
                    y_pred_list.append(y_pred[0])
                    #accuracy.append(metrics.accuracy_score(y_test,y_pred))
               # cnf_matrix = metrics.confusion_matrix(y,y_pred_list)
               # class_names = mapping_disease_for_labels.keys()
               # # # Plot non-normalized confusion matrix
               # plt.figure()
               # plot_confusion_matrix(cnf_matrix, classes=class_names,
               #                          title='Confusion matrix, without normalization')
               #
               # # # Plot normalized confusion matrix
               # plt.figure()
               # plot_confusion_matrix(cnf_matrix, classes=list(class_names), normalize=True,
               #                          title='Normalized confusion matrix')
               #
               # plt.show()
               scores = np.array(metrics.accuracy_score(y,y_pred_list))
               print(md, ne, lr,  round(scores.mean(),2), round(scores.std(),2) * 2)

#print(y_pred_list)
#print(x_indx)
#print(preproccessed_data.index.values)

predicted_data = preproccessed_data

predicted_data['pred'] = np.array(y_pred_list)
most_corelated_taxon = {}
for i in range(predicted_data.shape[1] - 1):
    if scipy.stats.spearmanr(predicted_data.iloc[:, i], predicted_data['pred'])[1]<0.05/predicted_data.shape[1]:
        most_corelated_taxon[predicted_data.columns[i]] = scipy.stats.spearmanr(predicted_data.iloc[:, i], predicted_data['pred'])[0]

sorted_taxon = sorted(most_corelated_taxon.items(), key=lambda x: abs(x[1]), reverse=True)
most_corelated_taxon = sorted_taxon[:50]

G=nx.Graph()
labeldict = {}
for i in range(len(most_corelated_taxon)):
    G.add_node(i+1, taxonomy = most_corelated_taxon[i][0])
    labeldict[i+1] = most_corelated_taxon[i][0]

for i in range(len(most_corelated_taxon)):
    for j in range(len(most_corelated_taxon)):
        if i!=j:
            if (scipy.stats.spearmanr(predicted_data.loc[:, most_corelated_taxon[i][0]], predicted_data.loc[:,most_corelated_taxon[j][0]])[1]) < 0.001/38 :
                #print(most_corelated_taxon[i][0], most_corelated_taxon[j][0])
                if not G.has_edge(i+1,j+1):
                    G.add_edge(i+1,j+1)
                #print(scipy.stats.spearmanr(predicted_data.loc[:, most_corelated_taxon[i][0]], predicted_data.loc[:,most_corelated_taxon[j][0]])[1],
                 #     scipy.stats.spearmanr(predicted_data.loc[:, most_corelated_taxon[i][0]],
                  #                          predicted_data.loc[:, most_corelated_taxon[j][0]])[0])

#nx.draw(G,  with_labels = True)
#print(nx.connected_components(G))
#print(nx.degree(G))
#print(sorted(i[1] for i in nx.degree(G)))
#print(nx.clustering(G))
#plt.show()
#print(G)
rel_dict = []
for i in nx.degree(G):
    #if i[1] != 0:
        print(i)
        print(labeldict[i[0]])
        rel_dict.append(labeldict[i[0]])

new_data = preproccessed_data[rel_dict]
#visualize_pca(new_data)
otu_after_pca, _ = apply_pca(new_data, n_components=2)
merged_data = otu_after_pca.join(OtuMf.mapping_file['DiagnosisGroup'])

merged_data.fillna(0)

mapping_disease_for_labels = {'Control':0,'Cirrhosis/HCC':1, 'PSC/PSC+IBD':2}
mapping_disease = {'Control':0,'Cirrhosis ':1, 'HCC':1, 'PSC+IBD':2,'PSC':2}
merged_data['DiagnosisGroup'] = merged_data['DiagnosisGroup'].map(mapping_disease)
merged_data = merged_data.join(OtuMf.mapping_file[['Age', 'BMI', 'FattyLiver','RegularExercise', 'Smoking']])
mappin_boolean = {'yes' :1, 'no': 0, 'Control': 0, '0':0, '1':1}
merged_data['FattyLiver'] = merged_data['FattyLiver'].map(mappin_boolean)
merged_data['RegularExercise'] = merged_data['RegularExercise'].map(mappin_boolean)
merged_data['Smoking'] = merged_data['Smoking'].map(mappin_boolean)

X = merged_data.loc[:, merged_data.columns != 'DiagnosisGroup']
y = merged_data['DiagnosisGroup']
regex = re.compile(r"\[|\]|<", re.IGNORECASE)
X.columns = [regex.sub("_", col) if any(x in str(col) for x in set(('[', ']', '<'))) else col for col in X.columns.values]

loo = LeaveOneOut()

for md in range(2,6):
    for ne in range (50,300,50):
        for lr in range (5, 20, 5):
               #for rg in range(250, 400, 25):
            accuracy = []
# # #             auc_train = []
# # #             auc = []
               #for i in range(0,40,2):
               #        X_train, X_test, y_train, y_test = train_test_split(
               #            merged_data.loc[:, merged_data.columns != 'DiagnosisGroup'], merged_data['DiagnosisGroup'],
               #            test_size=0.25, random_state=i)
            y_pred_list = []
            x_indx = []
            for train_index, test_index in loo.split(X):
                train_index=list(train_index)
                    #print("%s %s" % (train_index, test_index))
                X_train, X_test = X.iloc[train_index,:], X.iloc[test_index,:]
                y_train, y_test = y[train_index], y[test_index]
                model = XGBClassifier(max_depth=md,n_estimators = ne ,learning_rate = lr/100,  objective='multi:softmax' )
# # #                                           #objective= 'binary:logistic')
                model.fit(X_train, y_train)
                    #x_indx.append(X_test.index[0])
                y_pred = model.predict(X_test)
# # #                     #pred_train = model.predict_proba(X_train)[:, 1]
# # #                     #auc_train.append(metrics.roc_auc_score(y_train, pred_train))
# # #                     #y_pred = model.predict_proba(X_test)[:,1]
# # #                     #try:
# # #                     #    auc.append(metrics.roc_auc_score(y_test, y_pred))
# # #                     #except:
# # #                     #    continue
                y_pred_list.append(y_pred[0])
                #accuracy.append(metrics.accuracy_score(y_test,y_pred))

            scores = np.array(metrics.accuracy_score(y, y_pred_list))
            print(md, ne, lr, round(scores.mean(), 2), round(scores.std(), 2) * 2)
