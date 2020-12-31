import os
import random
from collections import Counter

import pandas as pd
from xgboost import XGBClassifier

from LearningMethods.create_otu_and_mapping_files import CreateOtuAndMappingFiles
from Plot import plot_heat_map_from_df
from Plot.plot_preproccess_evaluation import plot_task_comparision
from Preprocess import apply_pca, OtuMfHandler, preprocess_data
import numpy as np
from sklearn import svm, metrics, preprocessing
from sklearn.model_selection import train_test_split, LeaveOneOut
from LearningMethods.leave_two_out import LeaveTwoOut


def read_otu_and_mapping_files(otu_path, mapping_path, num_pca):
    otu_file = pd.read_csv(otu_path)
    otu_file = otu_file.set_index("ID")
    mapping_file = pd.read_csv(mapping_path)
    mapping_file = mapping_file.set_index("#SampleID")

    otu_ids = otu_file.index
    map_ids = mapping_file.index
    mutual_ids = [id for id in otu_ids if id in map_ids]
    X = otu_file.loc[mutual_ids]
    y_ = mapping_file.loc[mutual_ids]

    n = [i for i, item in zip(y_.index, y_["Tag"]) if pd.isna(item)]
    X = X.drop(n).iloc[:, 0:num_pca].values
    y = y_.drop(n)["Tag"].astype(int)

    # print(Counter(y))
    return np.array(X), np.array(y)


def get_train_test_auc_from_svm(otu_path, mapping_path, pca, algorithm="xgboost", method="fold", k=20):
    X, y = read_otu_and_mapping_files(otu_path, mapping_path, pca)
    # weights = get_weights(y)
    if algorithm == "svm":
        clf = svm.SVC(kernel='linear', C=100, class_weight='balanced')
    else:  # xgboost
        clf = XGBClassifier(max_depth=6, learning_rate=0.1,
                            gamma=100, booster='gblinear')
    y_trains, y_tests = [], []
    y_train_scores, y_test_scores, train_auc_list = [], [], []

    if method == "loo":
        loo = LeaveOneOut()
        train_auc, test_auc = leave_out_main(X, y, loo, clf, algorithm, y_tests, y_test_scores, train_auc_list)

    elif method == "lto":
        lto = LeaveTwoOut()
        train_auc, test_auc = leave_out_main(X, y, lto, clf, algorithm, y_tests, y_test_scores, train_auc_list)

    else:  # regular/balanced fold
        train_auc, test_auc = fold_main(X, y, method, k, clf, algorithm, y_trains, y_tests, y_train_scores, y_test_scores)

    return train_auc, test_auc


def leave_out_main(X, y, lo, clf, algo, y_tests, y_test_scores, train_auc_list):
    for train_index, test_index in lo.split(y):
        X_train, X_test, y_train, y_test = X[train_index], X[test_index], y[train_index], y[test_index]
        y_tests.append(y_test)

        # FIT
        clf.fit(X_train, y_train)
        if algo == "svm":
            test_score = clf.decision_function(X_test)
            train_score = clf.decision_function(X_train)
        else:  #xgboost
            test_score = clf.predict_proba(X_test)
            train_score = clf.predict_proba(X_train)

        y_test_scores.append(test_score)

        train_auc = metrics.roc_auc_score(y_train, train_score)
        train_auc_list.append(train_auc)

    # --------------------------------------------! AUC -----------------------------------------
    all_test_real_tags = np.array(y_tests).flatten()
    y_test_scores = np.array(y_test_scores).flatten()

    test_auc = metrics.roc_auc_score(all_test_real_tags, y_test_scores)
    train_auc = np.average(train_auc_list)

    return train_auc, test_auc


def fold_main(X, y, method, k, clf, algo, y_trains, y_tests, y_train_scores, y_test_scores):
    for i in range(k):
        if method == "balanced_fold":
            X_train, X_test, y_train, y_test = balanced_train_test_split(X, y)
        else:
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

        y_trains.append(y_train)
        y_tests.append(y_test)

        # FIT
        clf.fit(X_train, y_train)
        if algo == "svm":
            test_score = clf.decision_function(X_test)
            train_score = clf.decision_function(X_train)
        else:  #xgboost
            test_score = [p[1] for p in clf.predict_proba(X_test)]
            train_score = [p[1] for p in clf.predict_proba(X_train)]
        y_train_scores.append(train_score)
        y_test_scores.append(test_score)

        # --------------------------------------------! AUC -----------------------------------------
    all_y_train = np.array(y_trains).flatten()
    y_train_scores = np.array(y_train_scores).flatten()
    all_test_real_tags = np.array(y_tests).flatten()
    y_test_scores = np.array(y_test_scores).flatten()

    test_auc = metrics.roc_auc_score(all_test_real_tags, y_test_scores)
    train_auc = metrics.roc_auc_score(all_y_train, y_train_scores)

    return train_auc, test_auc


def balanced_train_test_split(X, y):
    idx = list(range(len(y)))
    y_pos_idx = [i for i, y in enumerate(y) if y == 1]
    y_neg_idx = [i for i, y in enumerate(y) if y == 0]
    pos_X = [X[i_pos] for i_pos in y_pos_idx]
    neg_X = [X[i_neg] for i_neg in y_neg_idx]
    pos_y = [1 for i in range(len(pos_X))]
    neg_y = [0 for i in range(len(neg_X))]

    pos_X_train, pos_X_test, pos_y_train, pos_y_test = train_test_split(pos_X, pos_y, test_size=0.2)
    neg_X_train, neg_X_test, neg_y_train, neg_y_test = train_test_split(neg_X, neg_y, test_size=0.2)
    X_train = pos_X_train + neg_X_train
    X_test = pos_X_test + neg_X_test
    y_train = pos_y_train + neg_y_train
    y_test = pos_y_test + neg_y_test

    train = [(tr, te) for tr, te in zip(X_train, y_train)]
    random.shuffle(train)
    X_train = [t[0] for t in train]
    y_train = [t[1] for t in train]

    test = [(tr, te) for tr, te in zip(X_test, y_test)]
    random.shuffle(test)
    X_test = [t[0] for t in test]
    y_test = [t[1] for t in test]

    return np.array(X_train), np.array(X_test), np.array(y_train), np.array(y_test)


def microbiome_preprocess(max_pca, tax_list, tag_list, old_preprocess=True, rho_pca_plots=False, evaluate=False, algo="svm", method="fold"):
    for tax in tax_list:
        for tag in tag_list:
            if old_preprocess:
                otu_file = "otu_id.csv"
                tag_file = tag + "_tag.csv"
                OtuMf = OtuMfHandler(otu_file, tag_file, from_QIIME=False, id_col='ID', taxonomy_col='taxonomy')

                preproccessed_data = preprocess_data(OtuMf.otu_file, preform_z_scoring=True, visualize_data=False,
                                                     taxnomy_level=tax,
                                                     preform_taxnomy_group=True)

                otu_after_pca_wo_taxonomy, pca_obj, _ = apply_pca(preproccessed_data, n_components=max_pca,
                                                                  visualize=False)
                folder = tag + "_tax_" + str(tax) + "_csv_files"
                otu_name = "old_processed_otu_" + tag + "_tax_" + str(tax) + ".csv"
                otu_after_pca_wo_taxonomy["ID"] = otu_after_pca_wo_taxonomy.index
                otu_after_pca_wo_taxonomy = otu_after_pca_wo_taxonomy.set_index("ID")
                if not os.path.exists(folder):
                    os.mkdir(folder)
                otu_after_pca_wo_taxonomy.to_csv(os.path.join(folder, otu_name))

            else:  # yoel new Preprocess
                # parameters for Preprocess
                preprocess_prms = {'taxonomy_level': tax, 'taxnomy_group': 'mean', 'epsilon': 0.1, 'normalization': 'log',
                                   'z_scoring': 'row', 'norm_after_rel': '', 'std_to_delete': 0, 'pca': max_pca}

                mapping_file = CreateOtuAndMappingFiles("otu.csv", tag + "_tag.csv")
                mapping_file.preprocess(preprocess_params=preprocess_prms, visualize=False)

                if rho_pca_plots:
                    folder = "preprocess_plots_" + tag + "_tag_tax_" + str(tax) + "_pca_" + str(max_pca)
                    mapping_file.rhos_and_pca_calculation(tag, preprocess_prms['taxonomy_level'], preprocess_prms['pca'],
                                                          os.path.join(folder, "rhos"), os.path.join(folder, "pca"))

                otu_path, tag_path, pca_path = mapping_file.csv_to_learn(tag + '_task', tag + "_tax_" + str(tax) + "_csv_files",
                                                                         tax, max_pca)
                print(otu_path)


    # compere tax level and number of pca component using certain svm model and compere results
    if evaluate:
        microbiome_preprocess_evaluation(pca_options=list(range(2, max_pca)),
                                         tax_options=tax_list,
                                         tag_options=tag_list,
                                         old_preprocess=old_preprocess,
                                         algo=algo,
                                         method=method)


def extra_features_preprocess(max_pca, tag_list, id_col_name, folder, df_path, results_path, evaluate=False, algo="svm", method="loo"):
    if not os.path.exists(folder):
        os.mkdir(folder)
    df = pd.read_csv(df_path)
    df = df.rename(columns={id_col_name: "ID"})
    df = df.set_index("ID")
    for tag in tag_list:
        df_after_pca, pca_obj, _ = apply_pca(df, max_pca)
        file_name = "Extra_features_" + tag + ".csv"
        df_after_pca.to_csv(os.path.join(folder, file_name))

    # compere number of pca component using certain svm model and compere results
    if evaluate:
        extra_features_preprocess_evaluation(folder,
                                             tag_options=tag_list,
                                             pca_options=list(range(2, max_pca)),
                                             results_path=results_path,
                                             algo=algo,
                                             method=method)


def microbiome_preprocess_evaluation(tag_options, pca_options, tax_options, algo="svm", method="fold", old_preprocess=True):
    results_path = "preprocess_evaluation_plots"
    for tag in tag_options:
        task_results = {}
        for tax in tax_options:
            for pca_n in pca_options:
                folder = tag + "_tax_" + str(tax) + "_csv_files"
                if old_preprocess:
                    otu_path = os.path.join(folder, "old_processed_otu_" + tag + "_tax_" + str(tax) + ".csv")

                    tag_path = os.path.join(tag + '_tag.csv')
                else:
                    otu_path = os.path.join(folder, 'OTU_merged_' + tag + "_task_tax_level_" + str(tax) +
                                            '_pca_' + str(pca_n) + '.csv')

                    tag_path = os.path.join(folder, 'Tag_file_' + tag + '_task.csv')

                train_auc, test_auc = get_train_test_auc_from_svm(otu_path, tag_path, pca_n, algorithm=algo, method=method)
                task_results[(tax, pca_n)] = (train_auc, test_auc)
        plot_task_comparision(task_results, results_path, tag + "_preprocess_evaluation_plots_" + algo + "_"
                              + method, pca_options, tax_options)


def extra_features_preprocess_evaluation(folder, tag_options, pca_options, results_path, algo="svm", method="fold"):
    for tag in tag_options:
        task_results = {}
        for pca_n in pca_options:
            features_path = os.path.join(folder, "Extra_features_" + tag + ".csv")
            tag_path = os.path.join(tag + '_tag.csv')
            train_auc, test_auc = get_train_test_auc_from_svm(features_path, tag_path, pca_n, method=method)
            task_results[pca_n] = (train_auc, test_auc)
        plot_task_comparision(task_results, results_path, tag + "_preprocess_evaluation_plots", pca_options)


def fill_and_normalize_extra_features(extra_features_df):
    for col in extra_features_df.columns:
        extra_features_df[col] = extra_features_df[col].replace(" ", np.nan)
        average = np.average(extra_features_df[col].dropna().astype(float))
        extra_features_df[col] = extra_features_df[col].replace(np.nan, average)
        # z-score on columns

    extra_features_df[:] = preprocessing.scale(extra_features_df, axis=1)
    return extra_features_df


def create_na_distribution_csv(df, sub_df_list, col_names, title, plot=True):
    folder = "na"

    results_df = pd.DataFrame(columns=["column_name"] + col_names)
    for col in df.columns:
        na_values_number = []
        na_values_percent = []
        for sub_data_df in sub_df_list:
            na_values = sub_data_df[col].isna().sum()
            na_values_number.append(na_values)
            na_values_percent.append(round(na_values / len(sub_data_df), 4))
        # results_df.loc[len(results_df)] = [col + ";na_number"] + na_values_number
        results_df.loc[len(results_df)] = [col] + na_values_percent

    results_df = results_df.set_index("column_name")
    results_df.to_csv(os.path.join(folder, title + "_feature_na_distribution.csv"))

    if plot:
        start = 0
        margin = 18
        for i in range(int(len(results_df) / margin) + 1):
            plot_heat_map_from_df(results_df[start:min(start + margin, len(results_df))],
                                  title.replace("_", " ") + " Feature NA Distribution Part " + str(i),
                                  "groups", "features", folder, pos_neg=False)
            start += margin


def create_csv_from_column(df, col_name, id_col_name, title):
    tag_df = pd.DataFrame(columns=["ID", "Tag"])
    tag_df["ID"] = df[id_col_name]
    tag_df["Tag"] = df[col_name]
    tag_df = tag_df.set_index("ID").replace(" ", "nan")
    tag_df.to_csv(title)


def create_tags_csv(df, id_col_name, tag_col_and_name_list):
    for tag, name in tag_col_and_name_list:
        create_csv_from_column(df, tag, name + "_tag.csv", id_col_name)

