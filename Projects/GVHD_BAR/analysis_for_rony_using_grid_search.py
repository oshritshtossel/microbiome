from Projects.GVHD_BAR.load_merge_otu_mf import OtuMfHandler
from Preprocess.preprocess import preprocess_data
import tensorflow as tf

tf.enable_eager_execution()
from tensorflow.contrib import autograph
from tensorflow.python.keras import optimizers, regularizers, callbacks
from Preprocess import tf_analaysis
from tensorflow.python.keras.losses import mean_squared_error
# from Preprocess.generate_N_colors import getDistinctColors, rgb2hex
from Preprocess.general import apply_pca, use_spearmanr, use_pearsonr, roc_auc, convert_pca_back_orig, \
    draw_horizontal_bar_chart  # sigmoid
from Preprocess.visualize_groups import plot_bars
from Preprocess.fit import fit_SVR, fit_random_forest
import pandas as pd
import math
import matplotlib.pyplot as plt
from sklearn.metrics import auc, roc_curve
from scipy.stats import pearsonr
import numpy as np
from sklearn import svm

from sklearn.utils import class_weight

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split, GridSearchCV, LeaveOneOut
from xgboost import XGBClassifier, XGBRegressor

import xgboost as xgb
import datetime
from GVHD_BAR.show_data import calc_results_and_plot
from GVHD_BAR.calculate_distances import calculate_distance
from GVHD_BAR.cluster_time_events import cluster_based_on_time
import os
from Preprocess import tf_analaysis
from tensorflow.python.keras import regularizers
import sys

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
RECORD = True
PLOT = False
USE_SIMILARITY = False
USE_CLUSTER = False
USE_CLOSEST_NEIGHBOR = False
USE_CERTAINTY = False
PLOT_INPUT_TO_NN_STATS = False
PREFORM_VAL = False

callbacks_ = callbacks.EarlyStopping(monitor='my_mse_loss',
                                     min_delta=0.5,
                                     patience=10,
                                     verbose=0, mode='auto')


# @autograph.convert()
def my_loss(y_true, y_pred):
    mse_loss = my_mse_loss(y_true, y_pred)

    time_sense_loss = y_true[:, 2] - y_pred[:, 1]  # Max_delta - predicted_delta should be negative
    tsls = time_sense_loss  # tf.square(time_sense_loss)

    return y_true[:, 4] * tsls + y_true[:, 3] * mse_loss


def my_mse_loss(y_true, y_pred):
    mse_loss = tf.reduce_mean(tf.square(y_true[:, 1] - y_pred[:, 1]))

    return mse_loss


def predict_get_spearman_value(X, y, regressor):
    predicted_y = regressor.predict(X)
    spearman_values = use_spearmanr(y, predicted_y)
    pearson_values = use_pearsonr(y, predicted_y)
    return predicted_y, spearman_values, pearson_values


def plot_fit(x, y, name):
    plt.scatter(x, y)
    plt.title('Age in days using \n' + name)
    plt.xlabel('Real')
    plt.ylabel('Predicted')


def plot_spearman_vs_params(spearman_values, label=None, plot=True):
    x_values = []
    y_values = []
    for i, spearman_value in enumerate(spearman_values):
        x_values.append(i)
        y_values.append(1 - spearman_value['spearman_rho'])
    if plot:
        plt.plot(x_values, y_values, label=label, linewidth=0.5)
        plt.title(r'$1-\rho$ vs params.json')
        plt.xlabel('sample #')
        plt.ylabel(r'$1-\rho$ value')
    return x_values, y_values


def get_datetime(date_str):
    if pd.isnull(date_str):
        date_str = '01/01/1900'
    return datetime.datetime.strptime(date_str, '%d/%m/%Y')


def get_days(days_datetime):
    return days_datetime.days


n_components = 20
taxnomy_level = 3
n = n_components
file_name = f'combined_only_report_n_comps_{n_components}_taxonomy_level_{taxnomy_level}_using_ronies_and_{n}_pca'
use_recorded = False

script_dir = sys.path[0]

if not use_recorded:
    OtuMf = OtuMfHandler(os.path.join(SCRIPT_DIR, 'ronies_Data', 'saliva_samples_231018.csv'),
                         os.path.join(SCRIPT_DIR, 'ronies_Data', 'saliva_samples_mapping_file_231018.csv'),
                         from_QIIME=True)

    OtuMf = OtuMfHandler(os.path.join(SCRIPT_DIR, 'learn dataset', 'mucositis_first_table_260219.csv'),
                         os.path.join(SCRIPT_DIR, 'learn dataset', 'mucositis_mapping_file_first_250219_numbers.csv'),
                         from_QIIME=True)

    OtuMf = OtuMfHandler(os.path.join(SCRIPT_DIR, 'combined_data', 'dataset' , 'mucositis_combine_table_260219.csv'),
                         os.path.join(SCRIPT_DIR,  'combined_data', 'dataset' , 'mucositis_mapping_file_combine_250219_numbers.csv'),
                         from_QIIME=True)


    preproccessed_data = preprocess_data(OtuMf.otu_file, visualize_data=False, taxnomy_level=taxnomy_level)
    otu_after_pca_wo_taxonomy, pca_obj, pca_str = apply_pca(preproccessed_data, n_components=n_components,
                                                            visualize=False)
    with open(f'{file_name}.txt', 'w') as f:
        f.write('-------------- REPORT --------------\n')
        f.write(f'Using taxonomy level of {taxnomy_level} \n')
        f.write(f'Using {n_components} PCA components \n')
        f.write(f'{pca_str}\n\n')

    with open(f'{file_name}_with_grid_results.txt', 'w') as f:
        f.write('-------------- REPORT --------------\n')
        f.write(f'Using taxonomy level of {taxnomy_level} \n')
        f.write(f'Using {n_components} PCA components \n')
        f.write(f'{pca_str}\n\n')

    with open(f'{file_name}_csv.txt', 'w') as f:
        str_to_write = '\t'.join(['Config', 'SVM best params.json', 'SVM best score',' SVM Val score','xg best params.json', 'xg best score',' xg Val score'])
        f.write(f'{str_to_write}\n')

    # otu_after_pca = OtuMf.add_taxonomy_col_to_new_otu_data(otu_after_pca_wo_taxonomy)
    # merged_data_after_pca = OtuMf.merge_mf_with_new_otu_data(otu_after_pca_wo_taxonomy)
    # merged_data_with_age = otu_after_pca_wo_taxonomy.join(OtuMf.mapping_file['age_in_days'])
    # merged_data_with_age = merged_data_with_age[merged_data_with_age.age_in_days.notnull()] # remove NaN days
    # merged_data_with_age_group = otu_after_pca_wo_taxonomy.join(OtuMf.mapping_file[['age_group', 'age_in_days','MouseNumber']])
    # merged_data_with_age_group = merged_data_with_age_group[merged_data_with_age_group.age_group.notnull()] # remove NaN days

    # OtuMf.mapping_file.apply(lambda x: -999 if x['Mucositis_Start'] is None else (datetime.datetime.strptime(x['DATE'], '%d/%m/%Y') - datetime.datetime.strptime(x['Mucositis_Start'], '%d/%m/%Y')).days)

    mapping_file_negative_day = OtuMf.mapping_file.loc[OtuMf.mapping_file['Day'] < 0]

    # create groups
    data_grouped = mapping_file_negative_day.groupby('Personal_ID')

    mapping_file_last_day_before_transplant = pd.DataFrame()
    for subject_id, subject_data in data_grouped:
        subject_data.sort_index(by='Day', ascending=False, inplace=True)
        mapping_file_last_day_before_transplant = mapping_file_last_day_before_transplant.append(subject_data.iloc[0])

# get the other columns that rony asked for
# ronies_file_path = os.path.join(SCRIPT_DIR, 'ronies_Data','muc_model_louzon_090119nam.xlsx')
# ronies_file = pd.read_excel(ronies_file_path).set_index('subject_id')

interesting_cols = [
    'age_at_transplantation',
    'conmeds_recent_abx_1_mo',
    'response_bin',
    'donor_match_num',
    'cond_intensity',
    'prophylaxis_bin',
    'habits_smoking_recent_past_month'
]




# ronies_file_only_interesting_cols = ronies_file[interesting_cols]
#
# # merge the cols from ronies file with mapping_file_last_day_before_transplant
# mapping_file_last_day_before_transplant['Personal_ID'] = mapping_file_last_day_before_transplant['Personal_ID'].astype(int)
# mapping_file_last_day_before_transplant = mapping_file_last_day_before_transplant.reset_index()
# mapping_file_last_day_before_transplant = mapping_file_last_day_before_transplant.set_index('Personal_ID')
# mapping_file_last_day_and_ronies_cols = mapping_file_last_day_before_transplant.join(ronies_file_only_interesting_cols)
# mapping_file_last_day_and_ronies_cols = mapping_file_last_day_and_ronies_cols.set_index('index')
# -Ramge
mapping_file_last_day_and_only_ronies_col = mapping_file_last_day_before_transplant[interesting_cols + ['Description']]

# join ronies cols with the pca
mapping_file_last_day_and_only_ronies_col_with_pca = mapping_file_last_day_and_only_ronies_col.join(
    otu_after_pca_wo_taxonomy)

# remove rows that have not got microbiome
mapping_file_last_day_and_only_ronies_col_with_pca = mapping_file_last_day_and_only_ronies_col_with_pca[
    mapping_file_last_day_and_only_ronies_col_with_pca[0].notnull()]

Original_y = mapping_file_last_day_and_only_ronies_col_with_pca['Description']
Original_X = mapping_file_last_day_and_only_ronies_col_with_pca.drop(['Description'], 1)

for col in interesting_cols:
    Original_y = Original_y[Original_X[col].notnull()]
    Original_X = Original_X[Original_X[col].notnull()]


### change intensity def (flu/treu 10 riic --> rtc ###

patients = ['010',
'015',
'038',
'067',
'072',
'080',
'087',
'088',
'095',
'107',
'109',
'110',
'168',
'177',
'186',
'188',
'208']

filterd = [Original_X.filter(regex=f'R{x}', axis=0) for x in patients]
filterd_idx =[]
for x in filterd:
    if not x.empty:
        filterd_idx.append(x.index[0])

a = Original_X.loc[filterd_idx]

a['cond_intensity'] = 2.0

Original_X.update(a)

######## VALIDATION ########
OtuMf = OtuMfHandler(os.path.join(SCRIPT_DIR, 'validatin dataset', 'mucositis_table_second_260219.csv'),
                     os.path.join(SCRIPT_DIR, 'validatin dataset', 'mucositis_mapping_file_second_numbers.csv'),
                     from_QIIME=True)
preproccessed_data, mean, std = preprocess_data(OtuMf.otu_file, visualize_data=False, taxnomy_level=taxnomy_level,
                                                return_mean_std=True)
otu_after_pca_wo_taxonomy, pca_obj, pca_str = apply_pca(preproccessed_data, n_components=n_components, visualize=False)

mapping_file_negative_day = OtuMf.mapping_file.loc[OtuMf.mapping_file['Day'] < 0]

# create groups
data_grouped = mapping_file_negative_day.groupby('Personal_ID')

mapping_file_last_day_before_transplant = pd.DataFrame()
for subject_id, subject_data in data_grouped:
    subject_data.sort_index(by='Day', ascending=False, inplace=True)
    mapping_file_last_day_before_transplant = mapping_file_last_day_before_transplant.append(subject_data.iloc[0])

# get the other columns that rony asked for
# ronies_file_path = os.path.join(SCRIPT_DIR, 'ronies_Data','muc_model_louzon_090119nam.xlsx')
# ronies_file = pd.read_excel(ronies_file_path).set_index('subject_id')

interesting_cols = [
    'age_at_transplantation',
    'conmeds_recent_abx_1_mo',
    'response_bin',
    'donor_match_num',
    'cond_intensity',
    'prophylaxis_bin',
    'habits_smoking_recent_past_month'
]

# ronies_file_only_interesting_cols = ronies_file[interesting_cols]
#
# # merge the cols from ronies file with mapping_file_last_day_before_transplant
# mapping_file_last_day_before_transplant['Personal_ID'] = mapping_file_last_day_before_transplant['Personal_ID'].astype(int)
# mapping_file_last_day_before_transplant = mapping_file_last_day_before_transplant.reset_index()
# mapping_file_last_day_before_transplant = mapping_file_last_day_before_transplant.set_index('Personal_ID')
# mapping_file_last_day_and_ronies_cols = mapping_file_last_day_before_transplant.join(ronies_file_only_interesting_cols)
# mapping_file_last_day_and_ronies_cols = mapping_file_last_day_and_ronies_cols.set_index('index')
# -Ramge
mapping_file_last_day_and_only_ronies_col = mapping_file_last_day_before_transplant[interesting_cols + ['Description']]

# join ronies cols with the pca
mapping_file_last_day_and_only_ronies_col_with_pca = mapping_file_last_day_and_only_ronies_col.join(
    otu_after_pca_wo_taxonomy)

# remove rows that have not got microbiome
mapping_file_last_day_and_only_ronies_col_with_pca = mapping_file_last_day_and_only_ronies_col_with_pca[
    mapping_file_last_day_and_only_ronies_col_with_pca[0].notnull()]

Original_y_val = mapping_file_last_day_and_only_ronies_col_with_pca['Description']
Original_X_val = mapping_file_last_day_and_only_ronies_col_with_pca.drop(['Description'], 1)

for col in interesting_cols:
    Original_X_val[col] = pd.to_numeric(Original_X_val[col], errors='coerce')
    Original_y_val = Original_y_val[Original_X_val[col].notnull()]
    Original_X_val = Original_X_val[Original_X_val[col].notnull()]

# set type of learners
types_of_input = ['microbiome', 'ronies_features', 'both']
types_of_prediction = ['0_1_or_2_4', '0_1_or_3_4']
types_of_subject_to_analyze = ['methotrexate', 'all']

# types_of_input = [f'ronies_and_only_{n}_pca']
# types_of_prediction = ['0_1_or_2_4', '0_2_or_3_4']
# types_of_subject_to_analyze = ['methotrexate' , 'all']
# types_of_prediction = ['0_1_or_2_4']
# types_of_subject_to_analyze = ['methotrexate']

# types_of_input = ['both']
# types_of_prediction = ['0_2_or_3_4']
# types_of_subject_to_analyze = ['all']
#
#
# types_of_input = ['ronies_features']
# types_of_prediction = ['0_1_or_2_4']
# types_of_subject_to_analyze = ['methotrexate' ]
#
#
# set type of learners
types_of_input = ['both', 'microbiome', 'ronies_features']
types_of_prediction = ['0_1_or_2_4', '0_1_or_3_4']
types_of_subject_to_analyze = ['methotrexate', 'all']

# types_of_input = ['microbiome']
# types_of_prediction = ['0_1_or_2_4', '0_1_or_3_4']
# types_of_subject_to_analyze = ['methotrexate', 'all']
#
# types_of_input = ['both']
# types_of_prediction = ['0_1_or_2_4', '0_1_or_3_4']
# types_of_subject_to_analyze = ['methotrexate', 'all']

# types_of_input = [f'ronies_and_only_{n}_pca']
# # types_of_prediction = ['0_1_or_2_4', '0_2_or_3_4']
# # types_of_subject_to_analyze = ['methotrexate' , 'all']
# types_of_prediction = ['0_1_or_2_4']
# types_of_subject_to_analyze = ['methotrexate']




for col in interesting_cols:
    Original_X[col] = pd.to_numeric(Original_X[col], errors='coerce')
    Original_y = Original_y_val[Original_X[col].notnull()]
    Original_X = Original_X_val[Original_X[col].notnull()]



starting_col = np.argwhere(Original_X.columns == 0).tolist()[0][0]

# ### combine the data ### (only for features...)
# Original_X = Original_X.append(Original_X_val)
# Original_y = Original_y.append(Original_y_val)


for type_of_input in types_of_input:
    if type_of_input == 'microbiome':
        X_based_on_type_of_input = Original_X.iloc[:, starting_col:starting_col + n_components]
        X_based_on_type_of_input_val = Original_X_val.iloc[:, starting_col:starting_col + n_components]

    elif type_of_input == 'ronies_features':
        X_based_on_type_of_input = Original_X.iloc[:, 0:starting_col]
        X_based_on_type_of_input_val = Original_X_val.iloc[:, 0:starting_col]

    elif type_of_input == 'both':
        X_based_on_type_of_input = Original_X
        X_based_on_type_of_input_val = Original_X_val

    elif type_of_input == f'ronies_and_only_{n}_pca':
        X_based_on_type_of_input = Original_X.iloc[:, 0:starting_col + n]
        X_based_on_type_of_input_val = Original_X_val.iloc[:, 0:starting_col + n]

    for type_of_prediction in types_of_prediction:
        if type_of_prediction == '0_1_or_2_4':
            y_based_on_type_of_prediction = (Original_y > 1).astype(int)
            y_based_on_type_of_prediction_val = (Original_y_val > 1).astype(int)

            class_0 = '0_1'
            class_1 = '2_4'
        elif type_of_prediction == '0_2_or_3_4':
            y_based_on_type_of_prediction = (Original_y > 2).astype(int)
            y_based_on_type_of_prediction_val = (Original_y_val > 2).astype(int)

            class_0 = '0_2'
            class_1 = '3_4'
        elif type_of_prediction == '0_1_or_3_4':

            type_of_prediction_mask = Original_y != 2
            Original_y = Original_y[type_of_prediction_mask]
            X_based_on_type_of_input = X_based_on_type_of_input[type_of_prediction_mask]
            y_based_on_type_of_prediction = (Original_y > 2).astype(int)

            type_of_prediction_mask = Original_y_val != 2
            Original_y_val = Original_y_val[type_of_prediction_mask]
            X_based_on_type_of_input_val=X_based_on_type_of_input_val[type_of_prediction_mask]
            y_based_on_type_of_prediction_val = (Original_y_val > 2).astype(int)


            class_0 = '0_1'
            class_1 = '3_4'

        for type_of_subject_to_analyze in types_of_subject_to_analyze:
            if type_of_subject_to_analyze == 'methotrexate':
                methotrexate_indicator = Original_X['prophylaxis_bin'].astype(bool)

                X = X_based_on_type_of_input.loc[methotrexate_indicator]
                if type_of_input != 'microbiome':
                    X = X.drop(['prophylaxis_bin'], axis=1)

                y = y_based_on_type_of_prediction.loc[methotrexate_indicator]

                methotrexate_indicator_val = Original_X_val['prophylaxis_bin'].astype(bool)
                X_val = X_based_on_type_of_input_val.loc[methotrexate_indicator_val]
                if type_of_input != 'microbiome':
                    X_val = X_val.loc[methotrexate_indicator_val].drop(['prophylaxis_bin'], axis=1)
                y_val = y_based_on_type_of_prediction_val.loc[methotrexate_indicator_val]
            elif type_of_subject_to_analyze == 'all':
                X = X_based_on_type_of_input
                y = y_based_on_type_of_prediction
                X_val = X_based_on_type_of_input_val
                y_val = y_based_on_type_of_prediction_val

            permutation = {'type_of_input': type_of_input, 'type_of_prediction': type_of_prediction,
                           'type_of_subject_to_analyze': type_of_subject_to_analyze}
            permutation_str = ', '.join([f'{key} = {val}' for key, val in permutation.items()])
            print(permutation_str)

            # start the actual prediction with X and y as inputs
            Cross_validation = 5
            svm_y_test_from_all_iter = None
            svm_y_score_from_all_iter = None
            svm_y_pred_from_all_iter = None

            nn_y_test_from_all_iter = None
            nn_y_score_from_all_iter = None
            nn_y_pred_from_all_iter = None

            xg_y_test_from_all_iter = None

            my_cv = LeaveOneOut()

            # Split the dataset in two equal parts
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=0)

            # SVM
            # {'C': 10, 'kernel': 'linear'}
            # Set the parameters by cross-validation
            tuned_parameters = [{'kernel': ['rbf'], 'gamma': [1e-3, 1e-4],
                                 'C': [1, 10, 100, 1000]},
                                {'kernel': ['linear'], 'C': [1, 10, 100, 1000]}]
            # tuned_parameters = [{'kernel': ['linear'], 'C': [1]}]

            svm_clf = GridSearchCV(svm.SVC(class_weight='balanced'), tuned_parameters, cv=5,
                                   scoring='roc_auc', return_train_score=True)

            svm_clf.fit(X, y)

            # for col in interesting_cols:
            #
            #     fig, ax = plt.subplots(2, 2)
            #     plot_bars(X, y, col, fig_subtitle=f'Train: {col}', ax=ax[0, :], axis_title='Train')
            #     plot_bars(X_val, y_val, col, fig_subtitle=f'Test: {col}', ax=ax[1, :], axis_title='Validation')
            #     fig.tight_layout()

            print(svm_clf.best_params_)
            print(svm_clf.best_score_)

            means_test = svm_clf.cv_results_['mean_test_score']
            stds_test = svm_clf.cv_results_['std_test_score']
            means_train = svm_clf.cv_results_['mean_train_score']
            stds_train = svm_clf.cv_results_['std_train_score']

            svm_conf_stats = ''
            for train_mean, train_std, test_mean, test_std, params in zip(means_train, stds_train, means_test,
                                                                          stds_test, svm_clf.cv_results_['params.json']):
                svm_conf_stats += ("Train: %0.3f (+/-%0.03f) , Test: %0.3f (+/-%0.03f) for %r \n" % (
                train_mean, train_std * 2, test_mean, test_std * 2, params))

            # entire_W = svm_clf.best_estimator_.coef_[0]
            # W_pca = entire_W[starting_col:starting_col + n_components]
            # bacteria_coeff = convert_pca_back_orig(pca_obj.components_, W_pca, original_names=preproccessed_data.columns[:], visualize=True)
            # draw_horizontal_bar_chart(entire_W[0:starting_col], interesting_cols,  title='Feature Coeff', ylabel='Feature', xlabel='Coeff Value', left_padding=0.3)



            # xgboost
            # Set the parameters by cross-validation
            tuned_parameters = [{'alpha': [0, 0.001, 0.01, 0.1, 1], 'n_estimators': [3, 5, 10],
                                 'reg_lambda': [0, 10, 20], 'max_depth': [3, 5, 10],
                                 'min_child_weight': [0.1, 1, 10, 20]}]

            # tuned_parameters = [{'alpha': [0], 'n_estimators': [10],
            #                      'reg_lambda': [0], 'max_depth': [5],
            #                      'min_child_weight': [0.1]}]

            xgboost_clf = GridSearchCV(XGBClassifier(class_weight='balanced'), tuned_parameters, cv=5,
                                       scoring='roc_auc', return_train_score=True)

            xgboost_clf.fit(X, y)
            print(xgboost_clf.best_params_)
            print(xgboost_clf.best_score_)

            means_test = xgboost_clf.cv_results_['mean_test_score']
            stds_test = xgboost_clf.cv_results_['std_test_score']
            means_train = xgboost_clf.cv_results_['mean_train_score']
            stds_train = xgboost_clf.cv_results_['std_train_score']

            xgboost_conf_stats = ''
            for train_mean, train_std, test_mean, test_std, params in zip(means_train, stds_train, means_test,
                                                                          stds_test, xgboost_clf.cv_results_['params.json']):
                xgboost_conf_stats += ("Train: %0.3f (+/-%0.03f) , Test: %0.3f (+/-%0.03f) for %r \n" % (
                    train_mean, train_std * 2, test_mean, test_std * 2, params))


            with open(f'{file_name}.txt', 'a') as f:
                f.write(f'\n------------------- {permutation_str} -------------------\n')
                f.write('\n----------- SVM -----------\n')
                f.write(f'Best prams - {svm_clf.best_params_} \n')
                f.write(f'Best score - {svm_clf.best_score_} \n')
                # f.write(f'\nGrid Search \n')
                # f.write(svm_conf_stats)

                if PREFORM_VAL:
                    y_true, y_pred = y_val, svm_clf.predict(X_val)
                    xgboost_class_report = classification_report(y_true, y_pred)
                    _, _, _, svm_roc_auc = roc_auc(y_true, y_pred, verbose=True, visualize=False,
                                                   graph_title='SVM\n' + permutation_str)

                    f.write(f'Validation score: {svm_roc_auc}\n')

                f.write('\n----------- xgboost -----------\n')
                f.write(f'Best prams - {xgboost_clf.best_params_} \n')
                f.write(f'Best score - {xgboost_clf.best_score_} \n')
                # f.write(f'\nGrid Search \n')
                # f.write(xgboost_conf_stats)
                if PREFORM_VAL:

                    y_true, y_pred = y_val, xgboost_clf.predict(X_val)
                    xgboost_class_report = classification_report(y_true, y_pred)
                    _, _, _, xgboost_roc_auc = roc_auc(y_true, y_pred, verbose=True, visualize=False,
                                                       graph_title='SVM\n' + permutation_str)
                    f.write(f'Validation score: {xgboost_roc_auc}\n')

            with open(f'{file_name}_with_grid_results.txt', 'a') as f:
                f.write(f'\n\------------------- {permutation_str} -------------------\n')
                f.write('\n----------- SVM -----------\n')
                f.write(f'Best prams - {svm_clf.best_params_} \n')
                f.write(f'Best score - {svm_clf.best_score_} \n')
                f.write(f'\nGrid Search \n')
                f.write(svm_conf_stats)
                if PREFORM_VAL:
                    f.write(f'Validation score: {svm_roc_auc}\n')



                f.write('\n----------- xgboost -----------\n')
                f.write(f'Best prams - {xgboost_clf.best_params_} \n')
                f.write(f'Best score - {xgboost_clf.best_score_} \n')
                f.write(f'\nGrid Search \n')
                f.write(xgboost_conf_stats)
                if PREFORM_VAL:
                    f.write(f'Validation score: {xgboost_roc_auc}\n')


                ### CSV Creation ###
                with open(f'{file_name}_csv.txt', 'a') as f:
                    str_to_write_list = [permutation_str, str(svm_clf.best_params_), str(svm_clf.best_score_)]

                    if PREFORM_VAL:
                        str_to_write_list.append(str(svm_roc_auc))
                    else:
                        str_to_write_list.append('')

                    str_to_write_list += [str(xgboost_clf.best_params_), str(xgboost_clf.best_score_)]

                    if PREFORM_VAL:
                        str_to_write_list.append(str(xgboost_roc_auc))
                    else:
                        str_to_write_list.append('')
                    str_to_write = '\t'.join(str_to_write_list)
                    f.write(f'{str_to_write}\n')




            # for iter_num in range(Cross_validation):
            #     # print(f'\n\n------------------------------\nIteration number {iter_num}')
            #     X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=1/Cross_validation, random_state=iter_num)

            # for idx in range(len(y)):
            #     # print(f'\n\n------------------------------\nIteration number {iter_num}')
            #     X_test = X.iloc[idx].to_frame().transpose()
            #     y_test = pd.Series(y.iloc[idx], [y.index[idx]])
            #     X_train = X.drop(X.index[idx])
            #     y_train = y.drop(y.index[idx])
            #
            #     # shuffle
            #     idx = np.random.permutation(X_train.index)
            #     X_train = X_train.reindex(idx)
            #     y_train = y_train.reindex(idx)
            #
            #     class_weights = class_weight.compute_class_weight('balanced',
            #                                                       np.unique(y_train),
            #                                                       y_train)
            #     # SVM
            #     clf = svm.SVC(kernel='linear', class_weight='balanced')
            #     clf.fit(X_train, y_train)
            #     y_score = clf.decision_function(X_test)
            #     y_pred = clf.predict(X_test)
            #
            #     # save the y_test and y_score
            #     if svm_y_test_from_all_iter is None:
            #         svm_y_test_from_all_iter = y_test.values
            #         svm_y_score_from_all_iter = y_score
            #         svm_y_pred_from_all_iter = y_pred
            #     else:
            #         svm_y_test_from_all_iter = np.append(svm_y_test_from_all_iter, y_test.values)
            #         svm_y_score_from_all_iter = np.append(svm_y_score_from_all_iter, y_score)
            #         svm_y_pred_from_all_iter = np.append(svm_y_pred_from_all_iter, y_pred)

            # NN
            # test_model = tf_analaysis.nn_model()
            # regularizer = regularizers.l2(0.1)
            # test_model.build_nn_model(hidden_layer_structure=[{'units': n_components},
            #                                                   {'units': n_components*2, 'activation': tf.nn.relu, 'kernel_regularizer': regularizer},
            #                                                   ({'rate': 0.5}, 'dropout'),
            #                                                   {'units': n_components*2, 'activation': tf.nn.relu,'kernel_regularizer': regularizer},
            #                                                   ({'rate': 0.5}, 'dropout'),
            #                                                   {'units': n_components * 2, 'activation': tf.nn.relu, 'kernel_regularizer': regularizer},
            #                                                   ({'rate': 0.5}, 'dropout'),
            #                                                   {'units': 1, 'activation': 'sigmoid'}])
            #
            # test_model.compile_nn_model(loss='binary_crossentropy', metrics=['accuracy'])
            # hist = test_model.train_model(X_train.values, y_train.values.astype(np.float), epochs=50, verbose=0, class_weight=class_weights)
            # print('Train evaluation')
            # test_model.evaluate_model(X_train.values, y_train.values.astype(np.float))
            # print('\n\nTest evaluation')
            # test_model.evaluate_model(X_test.values, y_test.values.astype(np.float))
            #
            #
            # y_score = test_model.model.predict_proba(X_test.values)
            # y_pred = (test_model.model.predict(X_test.values)>0.5).astype(int)
            #
            # # save the y_test and y_score
            # if nn_y_test_from_all_iter is None:
            #     nn_y_test_from_all_iter = y_test.values
            #     nn_y_score_from_all_iter = y_score
            #     nn_y_pred_from_all_iter = y_pred
            #
            # else:
            #     nn_y_test_from_all_iter = np.append(nn_y_test_from_all_iter, y_test.values)
            #     nn_y_score_from_all_iter = np.append(nn_y_score_from_all_iter, y_score)
            #     nn_y_pred_from_all_iter = np.append(nn_y_pred_from_all_iter, y_pred)

            # xgboost
            # xgboost_clf = XGBClassifier(class_weight='balanced')
            # xgboost_clf.fit(X_train, y_train)
            # y_score = xgboost_clf.predict_proba(X_test)
            # y_score = [x[1] for x in y_score]
            # y_pred = xgboost_clf.predict(X_test)
            # print(y_score)
            # print(y_pred)
            # print(y_test.values)
            #
            # # save the y_test and y_score
            # if xg_y_test_from_all_iter is None:
            #     xg_y_test_from_all_iter = y_test.values
            #     xg_y_score_from_all_iter = y_score
            #     xg_y_pred_from_all_iter = y_pred
            # else:
            #     xg_y_test_from_all_iter = np.append(xg_y_test_from_all_iter, y_test.values)
            #     xg_y_score_from_all_iter = np.append(xg_y_score_from_all_iter, y_score)
            #     xg_y_pred_from_all_iter = np.append(xg_y_pred_from_all_iter, y_pred)

            # roc_auc(y_test.values, y_score, visualize=True,
            #         graph_title='XGBoost\n' + permutation_str)
            # plt.show()
            # Compute ROC curve and ROC area for each class
            # print('*** SVM **** \n')
            # print(confusion_matrix(svm_y_test_from_all_iter, svm_y_pred_from_all_iter))
            # print(classification_report(svm_y_test_from_all_iter, svm_y_pred_from_all_iter))
            # fpr, tpr, thresholds, svm_roc_auc = roc_auc(svm_y_test_from_all_iter, svm_y_score_from_all_iter, visualize=True, graph_title='SVM\n'+ permutation_str)
            # print('******************* \n')
            # # plt.savefig('SVM'+permutation_str+'png')
            #
            # # print('\n *** NN **** \n')
            # # print(confusion_matrix(nn_y_test_from_all_iter, nn_y_pred_from_all_iter))
            # # print(classification_report(nn_y_test_from_all_iter, nn_y_pred_from_all_iter))
            # # fpr, tpr, thresholds, nn_roc_auc = roc_auc(nn_y_test_from_all_iter, nn_y_score_from_all_iter, visualize=True, graph_title='NN\n' + permutation_str)
            # # plt.show()
            # # print('******************* \n')
            #
            # print('\n *** XGboost **** \n')
            # print(confusion_matrix(xg_y_test_from_all_iter, xg_y_pred_from_all_iter))
            # print(classification_report(xg_y_test_from_all_iter, xg_y_pred_from_all_iter))
            # fpr, tpr, thresholds, nn_roc_auc = roc_auc(xg_y_test_from_all_iter, xg_y_score_from_all_iter, visualize=True, graph_title='XGboost\n' + permutation_str)
            # plt.show()
            # print('******************* \n')
            # # plt.savefig('xgboost'+permutation_str+'png')
