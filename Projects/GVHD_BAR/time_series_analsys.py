
# import tensorflow as tf
import time
# from tensorflow.python.keras import backend as K

# tf.enable_eager_execution()
# from tensorflow.python.keras import optimizers, regularizers, callbacks, losses
# from Preprocess import tf_analaysis

import pandas as pd
from xgboost import XGBRegressor
import numpy as np
import pickle

from sklearn.model_selection import train_test_split, GridSearchCV, LeaveOneOut

from GVHD_BAR.show_data import calc_results_and_plot
from GVHD_BAR.calculate_distances import calculate_distance
import os
from Preprocess.tf_functions import build_lstm_model, compile_model, my_loss_batch, my_loss, build_fnn_model




pd.options.mode.chained_assignment = None

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
RECORD = True
PLOT = False
USE_SIMILARITY = False
PLOT_INPUT_TO_NN_STATS = False


PADDED_VALUE = -999

def print_recursive(object_to_print, count=0):
    replace_char_list = ['_', ' ']
    spaces = count * ' '
    if type(object_to_print) is dict:
        count += 1
        for key, val in object_to_print.items():
            if key in ['mean_time_to_event', 'samples_number', 'squared_mean']:
                print(f'{spaces}{key.replace(replace_char_list[0], replace_char_list[1])}: {val}')
            else:
                print(f'{spaces}{key.replace(replace_char_list[0], replace_char_list[1])}')
                print_recursive(val, count=count)

    else:
        # spaces = (count-1) * '\t'+ ' '
        print(f'{spaces}{object_to_print}')

def stats_input(uncensored, censored, verbose=True):
    stats = {'uncensored': {'mean_time_to_event': uncensored['delta_time'].mean(),
                            'squared_mean': uncensored['delta_time'].mean() * uncensored['delta_time'].mean(),
                            'samples_number': uncensored.shape[0]},
             'censored': {'samples_number': 'Not using' if censored is None else censored.shape[0]}}
    if verbose:
        print('\n\nStats of subjects (Uncensored and Censored)\n'
              '-------------------------------------------')
        print_recursive(stats)
    return stats

# def my_loss(y_true, y_pred):
#     mse_loss = my_mse_loss(y_true, y_pred)
#
#     time_sense_loss = y_true[:, 2] - y_pred[:, 1]  # Max_delta - predicted_delta should be negative
#     tsls = time_sense_loss #tf.square(time_sense_loss)
#
#     return y_true[:, 4] * tsls + y_true[:, 3] * mse_loss
#
# def my_loss(y_true, y_pred):
#     mse_loss = my_mse_loss(y_true, y_pred)
#
#     time_sense_loss = y_true[:, 2] - y_pred[:, 1]  # Max_delta - predicted_delta should be negative
#     tsls = time_sense_loss #tf.square(time_sense_loss)
#
#     return y_true[:, 4] * tsls + y_true[:, 3] * mse_loss
#
#
# def my_loss_batch(y_true, y_pred):
#     batch_size = y_pred.shape[0]
#     steps_size = y_pred.shape[1]
#
#
#     loss = 0
#     total_samples_in_batches = 0
#     for sample_in_batch in range(batch_size):
#         single_y_true = y_true[sample_in_batch, :, :]
#         single_y_pred = y_pred[sample_in_batch, :, :]
#
#         mask = tf.reduce_all(tf.logical_not(tf.equal(single_y_true, PADDED_VALUE)),axis=1)
#
#         single_y_true = tf.boolean_mask(single_y_true, mask)
#         single_y_pred = tf.boolean_mask(single_y_pred, mask)
#
#         loss_per_seq = my_loss(single_y_true, single_y_pred)
#         loss += tf.reduce_sum(loss_per_seq)
#         total_samples_in_batches += tf.convert_to_tensor(single_y_true[:, 1].shape[0], preferred_dtype=tf.float32)
#
#     return loss / tf.cast(total_samples_in_batches, tf.float32)
#
# def my_mse_loss(y_true, y_pred):
#     mse_loss = tf.reduce_mean(losses.mean_squared_error(tf.expand_dims(y_true[:, 1], axis=-1), tf.expand_dims(y_pred[:, 1], axis=-1)))
#
#     return mse_loss

def time_series_using_xgboost(X, y,
                              alpha_list,
                              n_estimators_list,
                              min_child_weight_list,
                              reg_lambda_list,
                              max_depth_list,
                              cross_val_number=5,
                              X_train_censored=None,
                              y_train_censored=None,
                              record=RECORD,
                              grid_search_dir='grid_search_xgboost',
                              deep_verbose=False,
                              beta_for_similarity=None,
                              use_random_time=None):

    if len(y.shape) == 1:
        y = y.to_frame(name='delta_time')
        y_train_censored = y_train_censored if y_train_censored is None else y_train_censored.to_frame(name='delta_time')

    print(f'\nUsing xgboost analysis\n')
    stats_of_input = stats_input(y, y_train_censored, verbose=True)
    train_res, test_res = {}, {}
    for alpha in alpha_list:
        for n_estimators in n_estimators_list:
            for min_child_weight in min_child_weight_list:
                for reg_lambda in reg_lambda_list:
                    for max_depth in max_depth_list:
                        y_train_values = []
                        y_train_predicted_values = []

                        y_test_values = []
                        y_test_predicted_values = []

                        USE_CROSS_VAL = True
                        USE_LLO = False

                        if USE_CROSS_VAL:
                            number_iterations = cross_val_number
                        elif USE_LLO:
                            number_iterations = int(len(X))

                        current_configuration = {'alpha': alpha, 'n_estimators': n_estimators, 'min_child_weight': min_child_weight,
                                                 'reg_lambda': reg_lambda,'max_depth': max_depth}
                        if beta_for_similarity is not None:
                            current_configuration.update({'beta_for_similarity': beta_for_similarity})

                        current_configuration_str = '^'.join(
                            [str(key) + '=' + str(value) for key, value in current_configuration.items()])
                        print(f'Current config: {current_configuration}')

                        hist=[]
                        for i in range(number_iterations):

                            # sleep for random time to avoid collisions :O
                            # if use_random_time:
                            #     random_time_to_wait = random.random()
                            #     time.sleep(random_time_to_wait)

                            print('\nIteration number: ', str(i + 1))
                            if USE_CROSS_VAL:
                                X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

                            elif USE_LLO:
                                X_test = X.iloc[i].to_frame().transpose()
                                y_test = pd.Series(y.iloc[i], [y.index[i]])
                                X_train = X.drop(X.index[i])
                                y_train = y.drop(y.index[i])

                            # add censored
                            X_train = X_train.append(X_train_censored)
                            y_train = y_train.append(y_train_censored)

                            # shuffle
                            idx = np.random.permutation(X_train.index)
                            X_train = X_train.reindex(idx)
                            y_train = y_train.reindex(idx)


                            ### the actual regressor ###
                            xg_reg = XGBRegressor(objective='reg:linear', colsample_bytree=1, learning_rate=0.1,
                                                  reg_lambda=reg_lambda,
                                                  max_depth=max_depth, alpha=alpha, n_estimators=n_estimators,
                                                  min_child_weight=min_child_weight)
                            eval_set = [(X_train, y_train), (X_test, y_test)]
                            eval_metric = ["rmse"]

                            xg_reg.fit(X_train, y_train, eval_metric=eval_metric, eval_set=eval_set, verbose=deep_verbose)

                            tmp_eval = xg_reg.evals_result()
                            hist.append({'train': tmp_eval['validation_0']['rmse'][-1],
                                         'test': tmp_eval['validation_1']['rmse'][-1]})

                            y_train_values.append(y_train.values.ravel())
                            y_train_predicted_values.append(xg_reg.predict(X_train))

                            y_test_values.append(y_test.values.ravel())
                            y_test_predicted_values.append(xg_reg.predict(X_test))

                        #### END OF CONFIGURATION OPTION  ####
                        y_train_values = [item for sublist in y_train_values for item in sublist]
                        y_train_predicted_values = [item for sublist in y_train_predicted_values for item in sublist]

                        # remove the -1 values (the ones that are censored)
                        tmp = [i for i in zip(y_train_values, y_train_predicted_values) if int(i[0]) != -1]
                        y_train_values = [i[0] for i in tmp]
                        y_train_predicted_values = [i[1] for i in tmp]

                        y_test_values = [item for sublist in y_test_values for item in sublist]
                        y_test_predicted_values = [item for sublist in y_test_predicted_values for item in sublist]

                        current_train_res, current_test_res = calc_results_and_plot(y_train_values,
                                                                                    y_train_predicted_values,
                                                                                    y_test_values,
                                                                                    y_test_predicted_values,
                                                                                    algo_name='XGBoost',
                                                                                    visualize=PLOT,
                                                                                    title=f'Validation iterations: {number_iterations}',
                                                                                    show=False)

                        # print(current_train_res)
                        # print(current_test_res)
                        if record:
                            record_results(grid_search_dir,
                                           current_configuration_str,
                                           y_train_values,
                                           y_train_predicted_values,
                                           y_test_values,
                                           y_test_predicted_values,
                                           stats_of_input,
                                           current_train_res,
                                           current_test_res,
                                           hist)

                        train_res.update({current_configuration_str: current_train_res})
                        test_res.update({current_configuration_str: current_test_res})

    return train_res, test_res


def compute_time_for_censored_using_similarity_matrix(not_censored_data,
                                                      censored_data,
                                                      number_pca_used_in_data,
                                                      OtuMf,
                                                      otu_after_pca_wo_taxonomy,
                                                      beta,
                                                      remove_outliers=True,
                                                      th_value=None):

    print(f'Using similarity with beta = {beta}')

    # remove subects with no data in mocrobiome
    not_censored_data = not_censored_data.loc[not_censored_data[0].notnull()]
    before_removal = not_censored_data.shape[0]
    # remove outliers
    if remove_outliers:
        std = not_censored_data['time_for_the_event'].values.std()
        th = std * 5 if th_value is None else th_value

        outlier_mask = not_censored_data['time_for_the_event'] < th
        not_censored_data = not_censored_data.loc[outlier_mask]

        after_removal = not_censored_data.shape[0]
        print(f'Similarity outlier removal: {before_removal - after_removal} outlier/s were removed')

    def multiply_by_time_for_the_event(col):
        return col.apply(lambda x: x * col['time_for_the_event'])

    inputs = {subject_id: subject_data[list(range(number_pca_used_in_data))] for subject_id, subject_data in
              censored_data.items()}

    K, _ = calculate_distance(not_censored_data[list(range(number_pca_used_in_data))], inputs, beta, visualize=False)
    K_t_time = K.transpose().join(not_censored_data['time_for_the_event'])

    K_t_time_multiplied_time_for_the_event = K_t_time.apply(multiply_by_time_for_the_event, axis=1)

    denominator = K_t_time.sum()
    nominator = K_t_time_multiplied_time_for_the_event.sum()
    censored_time = nominator / denominator
    censored_data_with_time = OtuMf.mapping_file.loc[censored_time.index[:-1].tolist()]
    censored_data_with_time['time_for_the_event'] = censored_time

    censored_data_with_time = censored_data_with_time.join(otu_after_pca_wo_taxonomy)
    number_of_rows_before_removal = censored_data_with_time.shape[0]
    # remove subects with no data in mocrobiome
    censored_data_with_time = censored_data_with_time.loc[censored_data_with_time[0].notnull()]

    # remove subjects that are unable to calculate the synthetic time for the event
    censored_data_with_time = censored_data_with_time.loc[censored_data_with_time['time_for_the_event'].notnull()]
    number_of_rows_after_removal = censored_data_with_time.shape[0]
    removed_rows = number_of_rows_before_removal - number_of_rows_after_removal
    print(f'Removed {removed_rows} due to a problem with calculating synthetic time')

    return censored_data_with_time

def time_series_analysis_tf(X, y,
                            input_size,
                            l2_lambda_list,
                            dropout_list,
                            mse_factor_list,
                            number_layers_list,
                            number_neurons_per_layer_list,
                            epochs_list,
                            cross_val_number=5,
                            X_train_censored=None,
                            y_train_censored=None,
                            record=RECORD,
                            grid_search_dir='grid_search_tf',
                            beta_for_similarity=None,
                            censored_mse_fraction_factor=None,
                            early_stop_fraction=0.02,
                            min_epochs=10):

    print(f'\nUsing tf analysis\n')
    stats_of_input = stats_input(y, y_train_censored, verbose=True)
    train_res, test_res = {}, {}

    total_num_conf = len(l2_lambda_list)\
                     * len(dropout_list)\
                     * len(mse_factor_list)\
                     * len(number_layers_list)\
                     * len(number_neurons_per_layer_list)\
                     * len(epochs_list)
    config_count = 0
    time_stats = []
    for l2_lambda in l2_lambda_list:
        for dropout in dropout_list:
            for factor in mse_factor_list:
                for number_layers in number_layers_list:
                    for number_neurons_per_layer in number_neurons_per_layer_list:
                        for epochs in epochs_list:
                            # clear the model

                            y_train_values = []
                            y_train_predicted_values = []

                            y_test_values = []
                            y_test_predicted_values = []

                            USE_CROSS_VAL = True
                            USE_LLO = False

                            if USE_CROSS_VAL:
                                number_iterations = cross_val_number
                            elif USE_LLO:
                                number_iterations = int(len(X))

                            current_configuration = {'l2': l2_lambda, 'dropout': dropout, 'factor': factor, 'epochs': epochs,
                                                     'number_iterations': number_iterations, 'number_layers': number_layers, 'neurons_per_layer': number_neurons_per_layer}

                            if censored_mse_fraction_factor is not None:
                                # use mse factor of censored_mse_fraction_factor of the uncensored for the censored samples
                                y_train_censored['mse_coeff'].loc[y_train_censored[
                                                                      'mse_coeff'] == 'last_censored'] = factor / censored_mse_fraction_factor
                                current_configuration.update({'censored_mse_factor': factor / censored_mse_fraction_factor})

                            if beta_for_similarity is not None:
                                current_configuration.update({'beta_for_similarity': beta_for_similarity})

                            current_configuration_str = '^'.join(
                                [str(key) + '=' + str(value) for key, value in current_configuration.items()])
                            print(f'Current config: {current_configuration}')

                            config_count += 1
                            if config_count % 10 == 1:
                                start = time.clock()

                            algo_name = 'Neural Network'
                            test_model = build_fnn_model(number_neurons_per_layer, l2_lambda, input_size, number_layers,
                                                          dropout)
                            Wsave = test_model.model.get_weights()

                            print(f'\nConfiguration progress: {str(config_count)}/{total_num_conf} ({round(config_count / (total_num_conf), 3)}%)')

                            for i in range(number_iterations):
                                # print(Wsave)
                                test_model.model.set_weights(Wsave)
                                test_model.compile_nn_model(loss=my_loss, metrics=[my_loss])

                                print(f'CV Iteration number: {str(i + 1)}/{number_iterations}')
                                if USE_CROSS_VAL:
                                    y['mse_coeff'] = y['mse_coeff'].astype(float)
                                    y['mse_coeff'] = factor
                                    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

                                # elif USE_LLO:
                                #     X_test = X.iloc[i].to_frame().transpose()
                                #     y_test = pd.Series(y.iloc[i], [y.index[i]])
                                #     X_train = X.drop(X.index[i])
                                #     y_train = y.drop(y.index[i])

                                # add censored
                                X_train = X_train.append(X_train_censored)
                                y_train = y_train.append(y_train_censored)

                                # shuffle
                                idx = np.random.permutation(X_train.index)
                                X_train = X_train.reindex(idx)
                                y_train = y_train.reindex(idx)

                                hist = []
                                loss_best_epoch = None
                                count = 0
                                for epoch in range(epochs):
                                    save_and_break=False
                                    y_train_values_per_epoch = []
                                    y_train_predicted_values_per_epoch = []
                                    y_test_values_per_epoch = []
                                    y_test_predicted_values_per_epoch = []
                                    loss_last_epoch = 0
                                    hist.append(
                                        test_model.train_model(X_train.values,  y_train.values.astype(np.float), epochs=1, verbose=False,
                                                               batch_size=10).history)
                                    # if early_stop_fraction is not None:
                                    #     loss_last_epoch = hist[-1]['loss'][0]
                                    #
                                    #     if loss_best_epoch is None:
                                    #         loss_best_epoch = loss_last_epoch
                                    #     else:
                                    #         early_stop_fraction=0
                                    #
                                    #         if loss_last_epoch > loss_best_epoch:
                                    #             count += 1
                                    #             print(f'\nloss_best_epoch: {loss_best_epoch}')
                                    #             print(f'loss_last_epoch: {loss_last_epoch}')
                                    #             print(f'loss_last_epoch - loss_best_epoch: {loss_last_epoch - loss_best_epoch}')
                                    #             print(count)
                                    #         else:
                                    #             loss_best_epoch = loss_last_epoch
                                    #             count = 0
                                    #
                                    #         if count == min_epochs:
                                    #             print(f'\n***best epoch number = {epoch + 1 - (count - 1)}')
                                    #             save_and_break = True

                                            # if loss_last_epoch < 0.995*loss_best_epoch or :
                                            #     loss_best_epoch = loss_last_epoch
                                            #     count = 0
                                            # else:
                                            #     count += 1
                                            # if count == 20:
                                            #     print(f'\n***best epoch number = {epoch + 1 - (count - 1)}')
                                            #     save_and_break=True

                                    predicted_val = test_model.predict(X_train.values)
                                    y_train_values_per_epoch.append(y_train.values.astype(np.float))
                                    y_train_predicted_values_per_epoch.append(predicted_val)

                                    predicted_val = test_model.predict(X_test.values)
                                    y_test_values_per_epoch.append(y_test.values.astype(np.float))
                                    y_test_predicted_values_per_epoch.append(predicted_val)

                                    y_train_values_per_epoch = [item for sublist in y_train_values_per_epoch for item in sublist]
                                    y_train_predicted_values_per_epoch = [item for sublist in y_train_predicted_values_per_epoch for
                                                                item in sublist]

                                    # remove the -1 values (the ones that are censored)
                                    tmp = [i for i in zip(y_train_values_per_epoch, y_train_predicted_values_per_epoch) if
                                           int(i[0][1]) != -1]
                                    y_train_values_per_epoch = [i[0][1] for i in tmp]
                                    y_train_predicted_values_per_epoch = [i[1][1] for i in tmp]

                                    y_test_values_per_epoch = [item for sublist in y_test_values_per_epoch for item in sublist]
                                    y_test_predicted_values_per_epoch = [item for sublist in y_test_predicted_values_per_epoch for item
                                                               in sublist]

                                    y_test_values_per_epoch = [i[1] for i in y_test_values_per_epoch]
                                    y_test_predicted_values_per_epoch = [i[1] for i in y_test_predicted_values_per_epoch]



                                    # y_test_values = [item for sublist in y_test_values for item in sublist]
                                    # y_test_predicted_values = [item for sublist in y_test_predicted_values for item in sublist]
                                    # y_test_predicted_values = [item for sublist in y_test_predicted_values for item in sublist]

                                    current_train_res, current_test_res = calc_results_and_plot(
                                        y_train_values_per_epoch, y_train_predicted_values_per_epoch,
                                        y_test_values_per_epoch,
                                        y_test_predicted_values_per_epoch, algo_name='NeuralNetwork',
                                        visualize=PLOT,
                                        title=f'Epochs: {epochs}, Validation iterations: {number_iterations}',
                                        show=False)

                                    loss_last_epoch = current_train_res['mse']

                                    if loss_best_epoch is None:
                                        loss_best_epoch = loss_last_epoch
                                    else:
                                        print(f'\n epoch = {epoch}')
                                        print(f'loss_best_epoch: {loss_best_epoch}')
                                        print(f'loss_last_epoch: {loss_last_epoch}')
                                        if loss_last_epoch > loss_best_epoch:
                                            count += 1
                                            print(count)
                                        else:
                                            loss_best_epoch = loss_last_epoch
                                            count = 0

                                        if count == min_epochs:
                                            print(f'\n***best epoch number = {epoch - count}')
                                            save_and_break = True


                                    if epoch % 5 == 0 or save_and_break:
                                        print(f'{100 * epoch / epochs}%')
                                        if not os.path.exists(os.path.dirname(grid_search_dir)):
                                            os.mkdir(os.path.dirname(grid_search_dir))
                                        if not os.path.exists(grid_search_dir):
                                            os.mkdir(grid_search_dir)
                                        dir_to_save = os.path.join(grid_search_dir, f'{current_configuration_str}')
                                        if not os.path.exists(dir_to_save):
                                            os.mkdir(dir_to_save)
                                        dir_to_save = os.path.join(dir_to_save, f'cv_{i}')
                                        if not os.path.exists(dir_to_save):
                                            os.mkdir(dir_to_save)

                                        np.save(dir_to_save + f'\\y_train_values_epoch_{epoch}.npy',
                                                y_train_values_per_epoch)
                                        np.save(dir_to_save + f'\\y_train_predicted_values_epoch_{epoch}.npy',
                                                y_train_predicted_values_per_epoch)
                                        np.save(dir_to_save + f'\\y_test_values_epoch_{epoch}.npy',
                                                y_test_values_per_epoch)
                                        np.save(dir_to_save + f'\\y_test_predicted_values_epoch_{epoch}.npy',
                                                y_test_predicted_values_per_epoch)

                                        with open(dir_to_save + '\\' + 'grid_search_results.txt', 'a') as f:
                                            f.writelines(
                                                [f'Epoch{epoch}\n Train\n ', str(current_train_res), '\nTest\n ',
                                                 str(current_test_res),
                                                 '\n'])

                                    if save_and_break:
                                        break



                                    # y_train_predicted_values.append(test_model.predict(X_train.values)[:, 1])

                                predicted_val = test_model.predict(X_train.values)
                                y_train_values.append(y_train.values.astype(np.float))
                                y_train_predicted_values.append(predicted_val)

                                predicted_val = test_model.predict(X_test.values)
                                y_test_values.append(y_test.values.astype(np.float))
                                y_test_predicted_values.append(predicted_val)

                                # display time stats every 10 configs
                            if config_count % 10 == 1 or True:
                                elapsed = time.clock()
                                elapsed = elapsed - start
                                print(f'Last Configuration took {elapsed} seconds')
                                time_stats.append(elapsed)
                                print(f'\nMean time for measured configurations {sum(time_stats) / len(time_stats)} seconds\n')

                            #### END OF CONFIGURATION OPTION  ####
                            y_train_values = [item for sublist in y_train_values for item in sublist]
                            y_train_predicted_values = [item for sublist in y_train_predicted_values for item in sublist]

                            # remove the -1 values (the ones that are censored)
                            tmp = [i for i in zip(y_train_values, y_train_predicted_values) if
                                   int(i[0][1]) != -1]
                            y_train_values = [i[0][1] for i in tmp]
                            y_train_predicted_values = [i[1][1] for i in tmp]

                            y_test_values = [item for sublist in y_test_values for item in sublist]
                            y_test_predicted_values = [item for sublist in y_test_predicted_values
                                                                 for item
                                                                 in sublist]

                            y_test_values = [i[1] for i in y_test_values]
                            y_test_predicted_values = [i[1] for i in y_test_predicted_values]

                            current_train_res, current_test_res = calc_results_and_plot(y_train_values, y_train_predicted_values,
                                                                                        y_test_values,
                                                                                        y_test_predicted_values, algo_name='NeuralNetwork',
                                                                                        visualize=PLOT,
                                                                                        title=f'Epochs: {epochs}, Validation iterations: {number_iterations}',
                                                                                        show=False)

                            # print(current_train_res)
                            # print(current_test_res)
                            if record:
                                record_results(grid_search_dir,
                                               current_configuration_str,
                                               y_train_values,
                                               y_train_predicted_values,
                                               y_test_values,
                                               y_test_predicted_values,
                                               stats_of_input,
                                               current_train_res,
                                               current_test_res,
                                               hist)

                            train_res.update({current_configuration_str: current_train_res})
                            test_res.update({current_configuration_str: current_test_res})

    return train_res, test_res


def time_series_analysis_rnn(X, y,
                             input_size,
                             l2_lambda_list,
                             dropout_list,
                             mse_factor_list,
                             number_layers_list,
                             number_neurons_per_layer_list,
                             epochs_list,
                             cross_val_number=5,
                             X_train_censored=None,
                             y_train_censored=None,
                             record=RECORD,
                             grid_search_dir='grid_search_rnn',
                             beta_for_similarity=None,
                             censored_mse_fraction_factor=None,
                             batch_size=20,
                             early_stop_fraction=None,
                             min_epochs=10):

    print(f'\nUsing lstm analysis\n')
    stats_of_input = stats_input(y, y_train_censored, verbose=True)
    train_res, test_res = {}, {}

    total_num_conf = len(l2_lambda_list)\
                     * len(dropout_list)\
                     * len(mse_factor_list)\
                     * len(number_layers_list)\
                     * len(number_neurons_per_layer_list)\
                     * len(epochs_list)
    config_count=0
    time_stats = []
    for l2_lambda in l2_lambda_list:
        for dropout in dropout_list:
            for factor in mse_factor_list:
                for number_layers in number_layers_list:
                    for number_neurons_per_layer in number_neurons_per_layer_list:
                        for epochs in epochs_list:


                            # clear the model
                            # K.clear_session()

                            y_train_values = []
                            y_train_predicted_values = []

                            y_test_values = []
                            y_test_predicted_values = []

                            USE_CROSS_VAL = True
                            USE_LLO = False

                            if USE_CROSS_VAL:
                                number_iterations = cross_val_number
                            elif USE_LLO:
                                number_iterations = int(len(X))

                            current_configuration = {'l2': l2_lambda, 'dropout': dropout, 'factor': factor,
                                                     'epochs': epochs,
                                                     'number_iterations': number_iterations,
                                                     'number_layers': number_layers,
                                                     'neurons_per_layer': number_neurons_per_layer}

                            if epochs == 'MAX':
                                epochs = 10000

                            if censored_mse_fraction_factor is not None:
                                # use mse factor of censored_mse_fraction_factor of the uncensored for the censored samples
                                y_train_censored['mse_coeff'].loc[y_train_censored[
                                                                      'mse_coeff'] == 'last_censored'] = factor / censored_mse_fraction_factor
                                current_configuration.update({'censored_mse_factor': factor / censored_mse_fraction_factor})

                            if beta_for_similarity is not None:
                                current_configuration.update({'beta_for_similarity': beta_for_similarity})

                            current_configuration_str = '^'.join(
                                [str(key) + '=' + str(value) for key, value in current_configuration.items()])
                            print(f'Current config: {current_configuration}')


                            config_count += 1
                            if config_count % 10 == 1 or True:
                                start = time.clock()
                            print(f'\nConfiguration progress: {str(config_count)}/{total_num_conf} ({round(config_count / (total_num_conf), 3)}%)')



                            test_model = build_lstm_model(number_neurons_per_layer, l2_lambda, input_size, number_layers, dropout)

                            # test_model = tf_analaysis.nn_model()
                            # regularizer = regularizers.l2(l2_lambda)
                            #
                            # model_structure = [({'units': 10, 'input_shape': (None, input_size),
                            #                      'return_sequences': True}, 'LSTM')]
                            #
                            #
                            # for layer_idx in range(number_layers):
                            #     model_structure.append({'units': number_neurons_per_layer, 'activation': tf.nn.relu,
                            #                             'kernel_regularizer': regularizer})
                            #     model_structure.append(({'rate': dropout}, 'dropout'))
                            #
                            # model_structure.append({'units': 4, 'kernel_regularizer': regularizer})
                            # test_model.build_nn_model(hidden_layer_structure=model_structure)


                            Wsave = test_model.model.get_weights()

                            for i in range(number_iterations):
                                test_model.model.set_weights(Wsave)
                                test_model.compile_nn_model(loss=my_loss_batch, metrics=[my_loss_batch])

                                # name = input("press anykey to continue")
                                print(f'CV Iteration number: {str(i + 1)}/{number_iterations}')
                                if USE_CROSS_VAL:
                                    # to supress the warning about copy...
                                    y.loc[:, 'mse_coeff'] = y['mse_coeff'].astype(float)
                                    y['mse_coeff'] = factor


                                    # split the data such that a sample is only in one group, or the train or the test
                                    data_grouped = X.groupby('groupby')

                                    groups = list(data_grouped.groups.keys())

                                    shuffled_idx = list(np.random.permutation(len(groups)))
                                    X_train = pd.DataFrame()
                                    min_x_train_len = np.ceil(0.7 * len(X))
                                    for list_idx, idx in enumerate(shuffled_idx):
                                        group_name_to_take = groups[idx]
                                        shuffled_idx.pop(list_idx)
                                        group_to_take = data_grouped.get_group(group_name_to_take)
                                        X_train = X_train.append(group_to_take)
                                        if len(X_train) > min_x_train_len:
                                            break
                                    y_train = y.loc[X_train.index]

                                    X_test = pd.DataFrame()
                                    for list_idx, idx in enumerate(shuffled_idx):
                                        group_name_to_take = groups[idx]
                                        shuffled_idx.pop(list_idx)
                                        group_to_take = data_grouped.get_group(group_name_to_take)
                                        X_test = X_test.append(group_to_take)
                                    y_test = y.loc[X_test.index]



                                #
                                # idx_for_save = '4'
                                # with open(f'C:\\Users\\Bar\\Desktop\\testing\\inputs_iter_{idx_for_save}.p', 'wb') as f:
                                #     pickle.dump([X_train, y_train, X_test, y_test], f)

                                # with open(f'C:\\Users\\Bar\\Desktop\\testin_inputs\\inputs_iter_{grid_search_dir[-1]}.p', 'rb') as f:
                                #     [X_train, y_train, X_test, y_test] = pickle.load(f)

                                # add censored
                                X_train = X_train.append(X_train_censored)
                                y_train = y_train.append(y_train_censored)
                                algo_name = 'LSTM Network'


                                def sample_generator(inputs, targets, batch_size=None):
                                    data_grouped = inputs.groupby('groupby')

                                    keys, values = [], []
                                    for key, value in data_grouped.groups.items():
                                        keys.append(key)
                                        values.append(value)

                                    batch_size = len(keys) if batch_size is None else min(batch_size, len(keys))


                                    def chunks(l, n):
                                        # For item i in a range that is a length of l,
                                        for i in range(0, len(l), n):
                                            # Create an index range for l of n items:
                                            yield l[i:i + n]

                                    batches = list(chunks(keys, batch_size))

                                    timestep_in_group = [len(x) for x in list(values)]
                                    max_timestep_in_group = [np.max(x) for x in list(chunks(timestep_in_group, batch_size))]


                                    #just to get the shapes...
                                    subject_data = data_grouped.get_group(keys[0])
                                    x_time_step = subject_data.drop('groupby', axis=1)
                                    sample_targets = targets.loc[x_time_step.index].values

                                    for batch, max in zip(batches, max_timestep_in_group):
                                        x_batch_to_return = np.ndarray((len(batch), max, x_time_step.shape[1]))
                                        target_batch_to_return = np.ndarray((len(batch), max, sample_targets.shape[1]))
                                        for idx, group_in_batch  in enumerate(batch):
                                            subject_data = data_grouped.get_group(group_in_batch)
                                            x_time_step = subject_data.drop('groupby', axis=1)
                                            sample_targets = targets.loc[x_time_step.index].values
                                            x_time_step=x_time_step.values
                                            number_of_zero_rows = max - len(x_time_step)
                                            rows_to_add = np.zeros((number_of_zero_rows, x_time_step.shape[1]))
                                            x_time_step = np.vstack([x_time_step, rows_to_add])
                                            x_batch_to_return[idx, :, :] = x_time_step


                                            rows_to_add = PADDED_VALUE * np.ones((number_of_zero_rows, sample_targets.shape[1]))
                                            sample_targets_ = np.vstack([sample_targets, rows_to_add])
                                            target_batch_to_return[idx, :, :] = sample_targets_.astype(np.float)

                                        yield x_batch_to_return, target_batch_to_return

                                test_samples = list(sample_generator(X_test, y_test))


                                hist = []
                                loss_best_epoch = None
                                count = 0
                                for epoch in range(epochs):
                                    save_and_break=False
                                    y_train_values_per_epoch = []
                                    y_train_predicted_values_per_epoch = []
                                    y_test_values_per_epoch = []
                                    y_test_predicted_values_per_epoch = []
                                    train_samples = sample_generator(X_train, y_train, batch_size=batch_size)
                                    loss_last_epoch = 0
                                    for input_sample, target_sample in list(train_samples):
                                        # print(f'\n***Actual epoch number = {epoch+1}')
                                        hist.append(test_model.train_model(input_sample, target_sample, epochs=1, verbose=False, batch_size=batch_size).history)

                                    if True:
                                        loss_last_epoch = hist[-1]['loss'][0]
                                        # for input_sample, target_sample in test_samples:
                                        #     a = test_model.evaluate_model(input_sample, target_sample, verbose=False)
                                        #     loss_last_epoch += list(a[0].values())[0]
                                        #     # y_test_predicted_values.append(predicted_val[:, :, 1])
                                        if loss_best_epoch is None:
                                            loss_best_epoch = loss_last_epoch
                                        else:
                                            print(f'\n epoch = {epoch}')
                                            print(f'loss_best_epoch: {loss_best_epoch}')
                                            print(f'loss_last_epoch: {loss_last_epoch}')
                                            if loss_last_epoch > loss_best_epoch:
                                                count += 1
                                                print(count)
                                            else:
                                                loss_best_epoch = loss_last_epoch
                                                count = 0

                                            if count == min_epochs:
                                                print(f'\n***best epoch number = {epoch - count}')
                                                save_and_break = True

                                    if epoch % 5 == 0 or save_and_break:
                                        print(f'{100 * epoch / epochs}%')
                                        train_samples = sample_generator(X_train, y_train)
                                        for input_sample, target_sample in train_samples:
                                            predicted_val = test_model.predict(input_sample)
                                            for sample, pred_sample in zip(target_sample, predicted_val):
                                                for sequence, pred_seq in zip(sample, pred_sample):
                                                    if np.all(sequence != PADDED_VALUE):
                                                        y_train_values_per_epoch.append(sequence[1])
                                                        y_train_predicted_values_per_epoch.append(pred_seq[1])

                                        test_samples = sample_generator(X_test, y_test)
                                        for input_sample, target_sample in test_samples:
                                            predicted_val = test_model.predict(input_sample)
                                            for sample, pred_sample in zip(target_sample, predicted_val):
                                                for sequence, pred_seq in zip(sample, pred_sample):
                                                    if np.all(sequence != PADDED_VALUE):
                                                        y_test_values_per_epoch.append(sequence[1])
                                                        y_test_predicted_values_per_epoch.append(pred_seq[1])

                                        # remove the -1 values (the ones that are censored)
                                        tmp = [i for i in zip(y_train_values_per_epoch, y_train_predicted_values_per_epoch) if
                                               int(i[0]) != -1]
                                        y_train_values_per_epoch = [i[0] for i in tmp]
                                        y_train_predicted_values_per_epoch = [i[1] for i in tmp]

                                        # y_test_values = [item for sublist in y_test_values for item in sublist]
                                        # y_test_predicted_values = [item for sublist in y_test_predicted_values for item in sublist]
                                        # y_test_predicted_values = [item for sublist in y_test_predicted_values for item in sublist]

                                        current_train_res, current_test_res = calc_results_and_plot(
                                            y_train_values_per_epoch, y_train_predicted_values_per_epoch,
                                            y_test_values_per_epoch,
                                            y_test_predicted_values_per_epoch, algo_name='NeuralNetwork',
                                            visualize=PLOT,
                                            title=f'Epochs: {epochs}, Validation iterations: {number_iterations}',
                                            show=False)

                                        if not os.path.exists(os.path.dirname(grid_search_dir)):
                                            os.mkdir(os.path.dirname(grid_search_dir))
                                        if not os.path.exists(grid_search_dir):
                                            os.mkdir(grid_search_dir)
                                        dir_to_save = os.path.join(grid_search_dir,f'{current_configuration_str}')
                                        if not os.path.exists(dir_to_save):
                                            os.mkdir(dir_to_save)
                                        dir_to_save = os.path.join(dir_to_save,f'cv_{i}')
                                        if not os.path.exists(dir_to_save):
                                            os.mkdir(dir_to_save)

                                        np.save(dir_to_save + f'\\y_train_values_epoch_{epoch}.npy', y_train_values_per_epoch)
                                        np.save(dir_to_save + f'\\y_train_predicted_values_epoch_{epoch}.npy', y_train_predicted_values_per_epoch)
                                        np.save(dir_to_save + f'\\y_test_values_epoch_{epoch}.npy', y_test_values_per_epoch)
                                        np.save(dir_to_save + f'\\y_test_predicted_values_epoch_{epoch}.npy', y_test_predicted_values_per_epoch)

                                        with open(dir_to_save + '\\' + 'grid_search_results.txt', 'a') as f:
                                            f.writelines(
                                                [f'Epoch{epoch}\n Train\n ', str(current_train_res), '\nTest\n ', str(current_test_res),
                                                 '\n'])
                                    if save_and_break:
                                        break

                                # y_train_predicted_values.append(test_model.predict(X_train.values)[:, 1])
                                train_samples = sample_generator(X_train, y_train)
                                for input_sample, target_sample in train_samples:
                                    predicted_val = test_model.predict(input_sample)
                                    for sample, pred_sample in zip(target_sample, predicted_val):
                                        for sequence, pred_seq in zip(sample, pred_sample):
                                            if np.all(sequence != PADDED_VALUE):
                                                y_train_values.append(sequence[1])
                                                y_train_predicted_values.append(pred_seq[1])

                                # y_test_predicted_values.append(test_model.predict(X_test.values)[:, 1])
                                # test the model
                                test_samples = sample_generator(X_test, y_test)
                                for input_sample, target_sample in test_samples:
                                    predicted_val = test_model.predict(input_sample)
                                    for sample, pred_sample in zip(target_sample, predicted_val):
                                        for sequence, pred_seq in zip(sample, pred_sample):
                                            if np.all(sequence != PADDED_VALUE):
                                                y_test_values.append(sequence[1])
                                                y_test_predicted_values.append(pred_seq[1])

                            # display time stats every 10 configs
                            if config_count%10 == 1 or True:
                                elapsed = time.clock()
                                elapsed = elapsed - start
                                print(f'Last Configuration took {elapsed} seconds')
                                time_stats.append(elapsed)
                                print(f'\nMean time for measured configurations {sum(time_stats)/len(time_stats)} seconds\n')
                            #### END OF CONFIGURATION OPTION  ####
                            # y_train_values = [item for sublist in y_train_values for item in sublist]
                            # y_train_predicted_values = [item for sublist in y_train_predicted_values for item in sublist]
                            # y_train_predicted_values = [item for sublist in y_train_predicted_values for item in sublist]

                            # remove the -1 values (the ones that are censored)
                            tmp = [i for i in zip(y_train_values, y_train_predicted_values) if int(i[0]) != -1]
                            y_train_values = [i[0] for i in tmp]
                            y_train_predicted_values = [i[1] for i in tmp]

                            # y_test_values = [item for sublist in y_test_values for item in sublist]
                            # y_test_predicted_values = [item for sublist in y_test_predicted_values for item in sublist]
                            # y_test_predicted_values = [item for sublist in y_test_predicted_values for item in sublist]

                            current_train_res, current_test_res = calc_results_and_plot(y_train_values, y_train_predicted_values,
                                                                                        y_test_values,
                                                                                        y_test_predicted_values, algo_name='NeuralNetwork',
                                                                                        visualize=PLOT,
                                                                                        title=f'Epochs: {epochs}, Validation iterations: {number_iterations}',
                                                                                        show=False)

                            # print(current_train_res)
                            # print(current_test_res)
                            if record:
                                record_results(grid_search_dir,
                                               current_configuration_str,
                                               y_train_values,
                                               y_train_predicted_values,
                                               y_test_values,
                                               y_test_predicted_values,
                                               stats_of_input,
                                               current_train_res,
                                               current_test_res,
                                               hist)

                            train_res.update({current_configuration_str: current_train_res})
                            test_res.update({current_configuration_str: current_test_res})

    return train_res, test_res



# def time_series_analysis_rnn_(X, y,
#                             input_size,
#                             l2_lambda_list,
#                             dropout_list,
#                             mse_factor_list,
#                             number_layers_list,
#                             number_neurons_per_layer_list,
#                             epochs_list,
#                             cross_val_number=5,
#                             X_train_censored=None,
#                             y_train_censored=None,
#                             record=RECORD,
#                             grid_search_dir='grid_search_rnn',
#                             beta_for_similarity=None,
#                             censored_mse_fraction_factor=None):
#
#     print(f'\nUsing lstm analysis\n')
#     stats_of_input = stats_input(y, y_train_censored, verbose=True)
#     train_res, test_res = {}, {}
#
#     total_num_conf = len(l2_lambda_list)\
#                      * len(dropout_list)\
#                      * len(mse_factor_list)\
#                      * len(number_layers_list)\
#                      * len(number_neurons_per_layer_list)\
#                      * len(number_neurons_per_layer_list)
#     config_count=0
#     time_stats = []
#     for l2_lambda in l2_lambda_list:
#         for dropout in dropout_list:
#             for factor in mse_factor_list:
#                 for number_layers in number_layers_list:
#                     for number_neurons_per_layer in number_neurons_per_layer_list:
#                         for epochs in epochs_list:
#                             # clear the model
#                             K.clear_session()
#
#                             y_train_values = []
#                             y_train_predicted_values = []
#
#                             y_test_values = []
#                             y_test_predicted_values = []
#
#                             USE_CROSS_VAL = True
#                             USE_LLO = False
#
#                             if USE_CROSS_VAL:
#                                 number_iterations = cross_val_number
#                             elif USE_LLO:
#                                 number_iterations = int(len(X))
#
#                             current_configuration = {'l2': l2_lambda, 'dropout': dropout, 'factor': factor, 'epochs': epochs,
#                                                      'number_iterations': number_iterations, 'number_layers': number_layers, 'neurons_per_layer': number_neurons_per_layer}
#
#                             if censored_mse_fraction_factor is not None:
#                                 # use mse factor of censored_mse_fraction_factor of the uncensored for the censored samples
#                                 y_train_censored['mse_coeff'].loc[y_train_censored[
#                                                                       'mse_coeff'] == 'last_censored'] = factor / censored_mse_fraction_factor
#                                 current_configuration.update({'censored_mse_factor': factor / censored_mse_fraction_factor})
#
#                             if beta_for_similarity is not None:
#                                 current_configuration.update({'beta_for_similarity': beta_for_similarity})
#
#                             current_configuration_str = '^'.join(
#                                 [str(key) + '=' + str(value) for key, value in current_configuration.items()])
#                             print(f'Current config: {current_configuration}')
#
#
#                             config_count += 1
#                             if config_count % 10 == 1 or True:
#                                 start = time.clock()
#                             print(f'\nConfiguration progress: {str(config_count)}/{total_num_conf} ({round(config_count / (total_num_conf), 3)}%)')
#                             for i in range(number_iterations):
#                                 name = input("press anykey to continue")
#                                 print(f'CV Iteration number: {str(i + 1)}/{number_iterations}')
#                                 if USE_CROSS_VAL:
#                                     # to supress the warning about copy...
#                                     y.loc[:, 'mse_coeff'] = y['mse_coeff'].astype(float)
#                                     y['mse_coeff'] = factor
#
#
#                                     # split the data such that a sample is only in one group, or the train or the test
#                                     data_grouped = X.groupby('groupby')
#
#                                     groups = list(data_grouped.groups.keys())
#
#                                     shuffled_idx = list(np.random.permutation(len(groups)))
#                                     X_train = pd.DataFrame()
#                                     min_x_train_len = np.ceil(0.8 * len(X))
#                                     for idx in shuffled_idx:
#                                         group_name_to_take = groups[idx]
#                                         shuffled_idx.pop()
#                                         group_to_take = data_grouped.get_group(group_name_to_take)
#                                         X_train = X_train.append(group_to_take)
#                                         if len(X_train) > min_x_train_len:
#                                             break
#                                     y_train = y.loc[X_train.index]
#
#                                     X_test = pd.DataFrame()
#                                     for idx in shuffled_idx:
#                                         group_name_to_take = groups[idx]
#                                         shuffled_idx.pop()
#                                         group_to_take = data_grouped.get_group(group_name_to_take)
#                                         X_test = X_test.append(group_to_take)
#                                     y_test = y.loc[X_test.index]
#
#                                 # add censored
#                                 X_train = X_train.append(X_train_censored)
#                                 y_train = y_train.append(y_train_censored)
#
#
#
#                                 algo_name = 'LSTM Network'
#
#                                 test_model = tf_analaysis.nn_model()
#                                 regularizer = regularizers.l2(l2_lambda)
#
#                                 model_structure = [({'units': 2*input_size, 'input_shape': (None, input_size), 'return_sequences': True}, 'LSTM')]
#                                 for layer_idx in range(number_layers):
#                                     model_structure.append({'units': number_neurons_per_layer, 'activation': tf.nn.relu, 'kernel_regularizer': regularizer})
#                                     model_structure.append(({'rate': dropout}, 'dropout'))
#
#
#                                 model_structure.append({'units': 1, 'kernel_regularizer': regularizer})
#                                 test_model.build_nn_model(hidden_layer_structure=model_structure)
#
#                                 test_model.compile_nn_model(loss='mse', metrics=['mse'])
#
#                                 def sample_generator(inputs, targets, batch_size=1):
#                                     data_grouped = inputs.groupby('groupby')
#
#                                     keys, values = [], []
#                                     for key, value in data_grouped.groups.items():
#                                         keys.append(key)
#                                         values.append(value)
#
#                                     batch_size = min(batch_size, len(keys))
#
#                                     timestep_in_group = [len(x) for x in list(values)]
#                                     max_timestep_in_group = [np.max(x) for x in np.array_split(timestep_in_group, np.ceil(len(timestep_in_group)/batch_size))]
#                                     batches = np.array_split(keys, np.ceil(len(keys)/batch_size))
#
#                                     #just to get the shapes...
#                                     subject_data = data_grouped.get_group(keys[0])
#                                     x_time_step = subject_data.drop('groupby', axis=1)
#                                     sample_targets = targets.loc[x_time_step.index].values
#
#                                     for batch, max in zip(batches, max_timestep_in_group):
#                                         x_batch_to_return = np.ndarray((batch_size, max, x_time_step.shape[1]))
#                                         target_batch_to_return = np.ndarray((batch_size, max, sample_targets.shape[1]))
#                                         for idx, group_in_batch  in enumerate(batch):
#                                             subject_data = data_grouped.get_group(group_in_batch)
#                                             x_time_step = subject_data.drop('groupby', axis=1)
#                                             sample_targets = targets.loc[x_time_step.index].values
#                                             x_time_step=x_time_step.values
#                                             number_of_zero_rows = max - len(x_time_step)
#                                             rows_to_add = np.zeros((number_of_zero_rows, x_time_step.shape[1]))
#                                             x_time_step = np.vstack([x_time_step, rows_to_add])
#                                             x_batch_to_return[idx, :, :] = x_time_step
#
#
#                                             rows_to_add = PADDED_VALUE * np.ones((number_of_zero_rows, sample_targets.shape[1]))
#                                             sample_targets = np.vstack([sample_targets, rows_to_add])
#                                             target_batch_to_return[idx, :, :] = sample_targets.astype(np.float)
#
#                                         yield x_batch_to_return, target_batch_to_return
#
#                                     # for subject_id, subject_data in data_grouped:
#                                     #     # print(subject_data)
#                                     #     x_time_step = subject_data.drop('groupby', axis=1)
#                                     #     sample_targets = targets.loc[x_time_step.index]
#                                     #     input_shape = x_time_step.values.shape
#                                     #     target_shape = sample_targets.shape
#                                     #
#                                     #     x_time_step = x_time_step.values.reshape(1, input_shape[0], input_shape[1])
#                                     #     target = sample_targets.values.reshape(1, target_shape[0], target_shape[1]).astype(
#                                     #         np.float)
#                                     # yield x_time_step, target
#
#                                 batch_size = 35
#
#                                 for epoch in range(epochs):
#                                     train_samples = sample_generator(X_train, y_train, batch_size=batch_size)
#                                     for input_sample, target_sample in train_samples:
#                                         print(f'\nActual epoch number = {epoch+1}')
#                                         a = target_sample[:, :, 1].reshape(target_sample[:, :, 1].shape[0],
#                                                                        target_sample[:, :, 1].shape[1], -1)
#                                         hist = test_model.train_model(input_sample, a, epochs=1, verbose=True, batch_size=batch_size)
#
#                                 # plt.plot(hist.history['loss'])
#
#                                 # # test the model
#                                 # test_samples = sample_generator(X_test, y_test)
#                                 # for input_sample, target_sample in test_samples:
#                                 #     test_model.evaluate_model(input_sample, target_sample)
#
#                                 y_train_values.append(y_train.values[:, 1])
#
#                                 # y_train_predicted_values.append(test_model.predict(X_train.values)[:, 1])
#                                 train_samples = sample_generator(X_train, y_train)
#                                 for input_sample, target_sample in train_samples:
#                                     predicted_val = test_model.predict(input_sample)
#                                     y_train_predicted_values.append(predicted_val[:,:,1])
#
#                                 y_test_values.append(y_test.values[:, 1])
#
#                                 # y_test_predicted_values.append(test_model.predict(X_test.values)[:, 1])
#                                 # test the model
#                                 test_samples = sample_generator(X_test, y_test)
#                                 for input_sample, target_sample in test_samples:
#                                     predicted_val = test_model.predict(input_sample)
#                                     y_test_predicted_values.append(predicted_val[:,:,1])
#
#                             # display time stats every 10 configs
#                             if config_count%10 == 1 or True:
#                                 elapsed = time.clock()
#                                 elapsed = elapsed - start
#                                 print(f'Last Configuration took {elapsed} seconds')
#                                 time_stats.append(elapsed)
#                                 print(f'\nMean time for measured example_configurations.yml {sum(time_stats)/len(time_stats)} seconds\n')
#                             #### END OF CONFIGURATION OPTION  ####
#                             y_train_values = [item for sublist in y_train_values for item in sublist]
#                             y_train_predicted_values = [item for sublist in y_train_predicted_values for item in sublist]
#                             y_train_predicted_values = [item for sublist in y_train_predicted_values for item in sublist]
#
#                             # remove the -1 values (the ones that are censored)
#                             tmp = [i for i in zip(y_train_values, y_train_predicted_values) if int(i[0]) != -1]
#                             y_train_values = [i[0] for i in tmp]
#                             y_train_predicted_values = [i[1] for i in tmp]
#
#                             y_test_values = [item for sublist in y_test_values for item in sublist]
#                             y_test_predicted_values = [item for sublist in y_test_predicted_values for item in sublist]
#                             y_test_predicted_values = [item for sublist in y_test_predicted_values for item in sublist]
#
#                             current_train_res, current_test_res = calc_results_and_plot(y_train_values, y_train_predicted_values,
#                                                                                         y_test_values,
#                                                                                         y_test_predicted_values, algo_name='NeuralNetwork',
#                                                                                         visualize=PLOT,
#                                                                                         title=f'Epochs: {epochs}, Validation iterations: {number_iterations}',
#                                                                                         show=False)
#
#                             # print(current_train_res)
#                             # print(current_test_res)
#                             if record:
#                                 record_results(grid_search_dir,
#                                                current_configuration_str,
#                                                y_train_values,
#                                                y_train_predicted_values,
#                                                y_test_values,
#                                                y_test_predicted_values,
#                                                stats_of_input,
#                                                current_train_res,
#                                                current_test_res,
#                                                hist.history)
#
#                             train_res.update({current_configuration_str: current_train_res})
#                             test_res.update({current_configuration_str: current_test_res})
#
#     return train_res, test_res


def record_results(grid_search_dir,
                   current_configuration_str,
                   y_train_values,
                   y_train_predicted_values,
                   y_test_values,
                   y_test_predicted_values,
                   stats_of_input,
                   current_train_res,
                   current_test_res,
                   hist=None):

    config_dir = grid_search_dir + '/' + current_configuration_str
    if not os.path.exists(grid_search_dir):
        os.mkdir(grid_search_dir)
    if not os.path.exists(config_dir):
        os.mkdir(config_dir)
    np.save(config_dir + '/y_train_values.npy', y_train_values)
    np.save(config_dir + '/y_train_predicted_values.npy', y_train_predicted_values)
    np.save(config_dir + '/y_test_values.npy', y_test_values)
    np.save(config_dir + '/y_test_predicted_values.npy', y_test_predicted_values)
    np.save(grid_search_dir + '/stats.npy', stats_of_input)
    if hist is not None:
        with open(config_dir + '/' + 'hist_res.p', 'wb') as f:
            pickle.dump(hist, f)
    with open(grid_search_dir + '/' + 'grid_search_results.txt', 'a') as f:
        f.writelines(['\n', current_configuration_str, '\n', 'Train\n ', str(current_train_res), '\nTest\n ',
                      str(current_test_res), '\n'])
    with open(config_dir + '/' + 'grid_search_results.txt', 'a') as f:
        f.writelines(['Train\n ', str(current_train_res), '\nTest\n ', str(current_test_res), '\n'])