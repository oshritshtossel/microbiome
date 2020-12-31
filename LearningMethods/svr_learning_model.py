from pathlib import Path
from sklearn import svm
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix
from LearningMethods.simple_learning_model import SimpleLearningModel
import os
import pandas as pd
import numpy as np
from sklearn.metrics import precision_score
from sklearn.metrics import recall_score
from Plot import roc_auc, multi_class_roc_auc, edit_confusion_matrix, \
    print_confusion_matrix, calc_auc_on_flat_results


class SVRLearningModel(SimpleLearningModel):
    def __init__(self):
        super().__init__()

    def create_classifiers(self, params):  # suited for svm only
        optional_classifiers = []
        # create all possible classifiers
        for kernel in params['kernel']:
            for gamma in params['gamma']:
                for C in params['C']:
                    clf = svm.SVR(kernel=kernel, C=C, gamma=gamma)  # class_weight='balanced')
                    optional_classifiers.append(clf)

        return optional_classifiers

    def get_model_coeff(self, clf, pca_obj, pca_flag, binary_flag):  # suited for svm only
        if pca_flag:  # preformed PCA -> convert_pca_back_orig
            if binary_flag:
                c = clf.coef_.tolist()[0]
                coefficients = c[:pca_obj.n_components]
            else:  # multi-class
                c = clf.coef_.tolist()
                coefficients = [c_[:pca_obj.n_components] for c_ in c]

        else:  # didn't preformed PCA -> no need to convert_pca_back_orig, use original coefficients
            if binary_flag:
                c = clf.coef_.tolist()[0]
            else:  # multi-class
                c = clf.coef_.tolist()
            coefficients = [c_[:pca_obj.n_components] for c_ in c]
        return coefficients

    def fit(self, X, y, X_train_ids, X_test_ids, y_train_ids, y_test_ids, params, weights, bacteria, task_name_title, relative_path_to_save_results, pca_obj=None):
        if not os.path.exists(os.path.join(relative_path_to_save_results, "SVR")):
            os.makedirs(os.path.join(relative_path_to_save_results, "SVR"))
        os.chdir(os.path.join(os.path.abspath(os.path.curdir), relative_path_to_save_results, "SVR"))
        print("SVR...")

        # update each classifier results in a mutual file
        svr_results_file = Path("all_svr_results.csv")
        if not svr_results_file.exists():
            all_svr_results = pd.DataFrame(columns=['KERNEL', 'GAMMA', 'C',
                                                    'TRAIN-AUC', 'TRAIN-ACC',
                                                    'TEST-AUC', 'TEST-ACC',
                                                    'PRECISION', 'RECALL'])
            all_svr_results.to_csv(svr_results_file, index=False)

        optional_classifiers = self.create_classifiers(params)

        for clf in optional_classifiers:
            all_svr_results = pd.read_csv(svr_results_file)
            clf_folder_name = "k=" + clf.kernel + "_c=" + str(clf.C) + "_g=" + clf.gamma
            if not os.path.exists(clf_folder_name):
                os.makedirs(clf_folder_name)

            X_trains, X_tests, y_trains, y_tests, svm_coefs = [], [], [], [], []
            svm_y_test_from_all_iter, svm_y_score_from_all_iter = np.array([]), np.array([])
            svm_y_pred_from_all_iter, svm_class_report_from_all_iter = np.array([]), np.array([])
            train_accuracies, test_accuracies, confusion_matrixes, y_train_preds, y_train_scores,\
            y_test_preds , y_test_scores = [], [], [], [], [], [], []

            bacteria_coeff_average = []

            for i in range(params["K_FOLD"]):
                print('------------------------------\niteration number ' + str(i))
                X_train, X_test, y_train, y_test = X.loc[X_train_ids[i]], X.loc[X_test_ids[i]], y[y_train_ids[i]], y[y_test_ids[i]]
                X_trains.append(X_train)
                X_tests.append(X_test)
                y_trains.append(y_train)
                y_tests.append(y_test)

                # FIT
                clf.fit(X_train, y_train)
                # GET RESULTS
                y_score = clf.decision_function(X_test)
                y_pred = clf.predict(X_test)
                y_test_preds.append(y_pred)
                svm_class_report = classification_report(y_test, y_pred).split("\n")
                train_pred = clf.predict(X_train)
                train_score = clf.decision_function(X_train)
                y_train_preds.append(train_pred)
                y_train_scores.append(train_score)
                y_test_scores.append(y_score)
                # SAVE RESULTS
                train_accuracies.append(accuracy_score(y_train, train_pred))
                test_accuracies.append(accuracy_score(y_test, y_pred))
                confusion_matrixes.append(confusion_matrix(y_test, y_pred))


                self.save_y_test_and_score(y_test, y_pred, y_score, svm_class_report)
                # --------------------------------------------! COEFF PLOTS -----------------------------------------
                if params["create_coeff_plots"]:
                    svm_coefs, coefficients, bacteria_coeff_average = \
                        self.calc_bacteria_coeff_average(num_of_classes, pca_obj, bacteria, clf, svm_coefs, bacteria_coeff_average)

            # --------------------------------------------! AUC -----------------------------------------
            all_y_train = np.array(y_trains).flatten()
            all_predictions_train = np.array(y_train_preds).flatten()
            y_train_scores = np.array(y_train_scores).flatten()
            all_test_real_tags = np.array(y_tests).flatten()
            all_test_pred_tags = np.array(y_test_preds).flatten()
            y_test_scores = np.array(y_test_scores).flatten()

            train_auc, test_auc, train_rho, test_rho = \
                calc_auc_on_flat_results(all_y_train, y_train_scores,
                                           all_test_real_tags, y_test_scores)

            # ----------------------------------------! CONFUSION MATRIX -------------------------------------
            print("------------------------------")
            names = params["CLASSES_NAMES"]
            confusion_matrix_average, confusion_matrix_acc = edit_confusion_matrix(confusion_matrixes,
                                                                            "SVM", names, BINARY=BINARY)

            res_path = clf_folder_name
            if not os.path.exists(res_path):
                os.mkdir(res_path)

            if params["create_coeff_plots"]:
                self.plot_bacteria_coeff_average(bacteria_coeff_average, len(set(y)), params["TASK_TITLE"], clf_folder_name,
                                            bacteria, params["K_FOLD"], "svr", res_path, False, names)



            # ----------------------------------------! SAVE RESULTS -------------------------------------
            self.save_results(task_name_title, train_auc, test_auc, train_rho, test_rho, confusion_matrix_average,
                         confusion_matrix_acc,
                         train_accuracies, test_accuracies, svr_y_score_from_all_iter, svr_y_pred_from_all_iter,
                         svr_y_test_from_all_iter, "SVR", res_path)

            all_svr_results.loc[len(all_svr_results)] = [clf.kernel, clf.C, clf.gamma, svr_train_roc_auc,
                                                         np.mean(train_accuracies), svr_roc_auc,
                                                             np.mean(test_accuracies),
                                                             precision_score(all_test_real_tags.astype(int), all_test_pred_tags,  average='micro'),
                                                             recall_score(all_test_real_tags.astype(int),  all_test_pred_tags, average='micro')]

            all_svr_results = all_svr_results.sort_values(by=['TEST-ACC'], ascending=False)

            all_svr_results.to_csv(svr_results_file, index=False)

