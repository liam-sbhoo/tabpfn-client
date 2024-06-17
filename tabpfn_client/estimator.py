from typing import Optional, Tuple, Literal, Dict
import logging
from dataclasses import dataclass, asdict

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin, RegressorMixin
from sklearn.utils.validation import check_is_fitted

from tabpfn_client import config

logger = logging.getLogger(__name__)


@dataclass(eq=True, frozen=True)
class PreprocessorConfig:
    """
    Configuration for data preprocessors.

    Attributes:
        name (Literal): Name of the preprocessor.
        categorical_name (Literal): Name of the categorical encoding method. Valid options are "none", "numeric",
                                "onehot", "ordinal", "ordinal_shuffled". Default is "none".
        append_original (bool): Whether to append the original features to the transformed features. Default is False.
        subsample_features (float): Fraction of features to subsample. -1 means no subsampling. Default is -1.
        global_transformer_name (str): Name of the global transformer to use. Default is None.
    """

    name: Literal[
        "per_feature",  # a different transformation for each feature
        "power",  # a standard sklearn power transformer
        "safepower",  # a power transformer that prevents some numerical issues
        "power_box",
        "safepower_box",
        "quantile_uni_coarse",  # different quantile transformations with few quantiles up to a lot
        "quantile_norm_coarse",
        "quantile_uni",
        "quantile_norm",
        "quantile_uni_fine",
        "quantile_norm_fine",
        "robust",  # a standard sklearn robust scaler
        "kdi",
        "none",  # no transformation (inside the transformer we anyways do a standardization)
        "kdi_random_alpha",
        "kdi_uni",
        "kdi_random_alpha_uni",
        "adaptive",
        "norm_and_kdi",
        # KDI with alpha collection
        "kdi_alpha_0.3_uni",
        "kdi_alpha_0.5_uni",
        "kdi_alpha_0.8_uni",
        "kdi_alpha_1.0_uni",
        "kdi_alpha_1.2_uni",
        "kdi_alpha_1.5_uni",
        "kdi_alpha_2.0_uni",
        "kdi_alpha_3.0_uni",
        "kdi_alpha_5.0_uni",
        "kdi_alpha_0.3",
        "kdi_alpha_0.5",
        "kdi_alpha_0.8",
        "kdi_alpha_1.0",
        "kdi_alpha_1.2",
        "kdi_alpha_1.5",
        "kdi_alpha_2.0",
        "kdi_alpha_3.0",
        "kdi_alpha_5.0",
    ]
    categorical_name: Literal[
        "none",
        "numeric",
        "onehot",
        "ordinal",
        "ordinal_shuffled",
        "ordinal_very_common_categories_shuffled",
    ] = "none"
    # categorical_name meanings:
    # "none": categorical features are pretty much treated as ordinal, just not resorted
    # "numeric": categorical features are treated as numeric, that means they are also power transformed for example
    # "onehot": categorical features are onehot encoded
    # "ordinal": categorical features are sorted and encoded as integers from 0 to n_categories - 1
    # "ordinal_shuffled": categorical features are encoded as integers from 0 to n_categories - 1 in a random order
    append_original: bool = False
    subsample_features: Optional[float] = -1
    global_transformer_name: Optional[str] = None
    # if True, the transformed features (e.g. power transformed) are appended to the original features

    def __str__(self):
        return (
            f"{self.name}_cat:{self.categorical_name}"
            + ("_and_none" if self.append_original else "")
            + (
                "_subsample_feats_" + str(self.subsample_features)
                if self.subsample_features > 0
                else ""
            )
            + (
                f"_global_transformer_{self.global_transformer_name}"
                if self.global_transformer_name is not None
                else ""
            )
        )

    def can_be_cached(self):
        return not self.subsample_features > 0

    def to_dict(self):
        return {
            k: str(v) if not isinstance(v, (str, int, float, list, dict)) else v
            for k, v in asdict(self).items()
        }


class TabPFNClassifier(BaseEstimator, ClassifierMixin):
    def __init__(
        self,
        model="latest_tabpfn_hosted",
        n_estimators: int = 4,
        preprocess_transforms: Tuple[PreprocessorConfig, ...] = (
            PreprocessorConfig(
                "quantile_uni_coarse",
                append_original=True,
                categorical_name="ordinal_very_common_categories_shuffled",
                global_transformer_name="svd",
                subsample_features=-1,
            ),
            PreprocessorConfig(
                "none", categorical_name="numeric", subsample_features=-1
            ),
        ),
        feature_shift_decoder: str = "shuffle",
        normalize_with_test: bool = False,
        average_logits: bool = False,
        optimize_metric: Literal[
            "auroc", "roc", "auroc_ovo", "balanced_acc", "acc", "log_loss", None
        ] = "roc",
        transformer_predict_kwargs: Optional[dict] = None,
        multiclass_decoder="shuffle",
        softmax_temperature: Optional[float] = -0.1,
        use_poly_features=False,
        max_poly_features=50,
        remove_outliers=12.0,
        add_fingerprint_features=True,
        subsample_samples=-1,
    ):
        """
        Parameters:
            model: The model string is the path to the model.
            n_estimators: The number of ensemble configurations to use, the most important setting.
            preprocess_transforms: A tuple of strings, specifying the preprocessing steps to use.
                You can use the following strings as elements '(none|power|quantile|robust)[_all][_and_none]', where the first
                part specifies the preprocessing step and the second part specifies the features to apply it to and
                finally '_and_none' specifies that the original features should be added back to the features in plain.
                Finally, you can combine all strings without `_all` with `_onehot` to apply one-hot encoding to the categorical
                features specified with `self.fit(..., categorical_features=...)`.
            feature_shift_decoder: ["shuffle", "none", "local_shuffle", "rotate", "auto_rotate"] Whether to shift features for each ensemble configuration.
            normalize_with_test: If True, the test set is used to normalize the data, otherwise the training set is used only.
            average_logits: Whether to average logits or probabilities for ensemble members.
            optimize_metric: The optimization metric to use.
            transformer_predict_kwargs: Additional keyword arguments to pass to the transformer predict method.
            multiclass_decoder: The multiclass decoder to use.
            softmax_temperature: A log spaced temperature, it will be applied as logits <- logits/exp(softmax_temperature).
            use_poly_features: Whether to use polynomial features as the last preprocessing step.
            max_poly_features: Maximum number of polynomial features to use.
            remove_outliers: If not 0.0, will remove outliers from the input features, where values with a standard deviation larger than remove_outliers will be removed.
            add_fingerprint_features: If True, will add one feature of random values, that will be added to the input features. This helps discern duplicated samples in the transformer model.
            subsample_samples: If not None, will use a random subset of the samples for training in each ensemble configuration. If 1 or above, this will subsample to the specified number of samples. If in 0 to 1, the value is viewed as a fraction of the training set size.
        """
        self.model = model
        self.n_estimators = n_estimators
        self.preprocess_transforms = preprocess_transforms
        self.feature_shift_decoder = feature_shift_decoder
        self.normalize_with_test = normalize_with_test
        self.average_logits = average_logits
        self.optimize_metric = optimize_metric
        self.transformer_predict_kwargs = transformer_predict_kwargs
        self.multiclass_decoder = multiclass_decoder
        self.softmax_temperature = softmax_temperature
        self.use_poly_features = use_poly_features
        self.max_poly_features = max_poly_features
        self.remove_outliers = remove_outliers
        self.add_fingerprint_features = add_fingerprint_features
        self.subsample_samples = subsample_samples

        # check if user is verified
        if config.g_tabpfn_config.user_email and not config.g_tabpfn_config.user_auth_handler.get_user_email_verification_status(config.g_tabpfn_config.user_email):
            raise RuntimeError(
                "Dear User, your email has not been verified. Please, check your mailbox, verify your email and try again!"
            )

    def fit(self, X, y):
        # assert init() is called
        if not config.g_tabpfn_config.is_initialized:
            raise RuntimeError(
                "tabpfn_client.init() must be called before using TabPFNClassifier"
            )

        if config.g_tabpfn_config.use_server:
            try:
                assert (
                    self.model == "latest_tabpfn_hosted"
                ), "Only 'latest_tabpfn_hosted' model is supported at the moment for init(use_server=True)"
            except AssertionError as e:
                print(e)
            config.g_tabpfn_config.inference_handler.fit(X, y)
            self.fitted_ = True
        else:
            raise NotImplementedError(
                "Only server mode is supported at the moment for init(use_server=False)"
            )
        return self

    def predict(self, X):
        probas = self.predict_proba(X)
        return np.argmax(probas, axis=1)

    def predict_proba(self, X):
        check_is_fitted(self)
        return config.g_tabpfn_config.inference_handler.predict(
            X, task="classification", config=self.get_params()
        )["probas"]


class TabPFNRegressor(BaseEstimator, RegressorMixin):
    def __init__(
        self,
        model: str = "latest_tabpfn_hosted",
        n_estimators: int = 8,
        preprocess_transforms: Tuple[PreprocessorConfig, ...] = (
            PreprocessorConfig(
                "quantile_uni",
                append_original=True,
                categorical_name="ordinal_very_common_categories_shuffled",
                global_transformer_name="svd",
            ),
            PreprocessorConfig("safepower", categorical_name="onehot"),
        ),
        feature_shift_decoder: str = "shuffle",
        normalize_with_test: bool = False,
        average_logits: bool = False,
        optimize_metric: Literal[
            "mse", "rmse", "mae", "r2", "mean", "median", "mode", "exact_match", None
        ] = "rmse",
        transformer_predict_kwargs: Optional[Dict] = None,
        softmax_temperature: Optional[float] = -0.1,
        use_poly_features=False,
        max_poly_features=50,
        remove_outliers=-1,
        regression_y_preprocess_transforms: Optional[
            Tuple[
                None
                | Literal[
                    "safepower",
                    "power",
                    "quantile_norm",
                ],
                ...,
            ]
        ] = (
            None,
            "safepower",
        ),
        add_fingerprint_features: bool = True,
        cancel_nan_borders: bool = True,
        super_bar_dist_averaging: bool = False,
        subsample_samples: float = -1,
    ):
        """
        Parameters:
            model: The model string is the path to the model.
            n_estimators: The number of ensemble configurations to use, the most important setting.
            preprocess_transforms: A tuple of strings, specifying the preprocessing steps to use.
                You can use the following strings as elements '(none|power|quantile_norm|quantile_uni|quantile_uni_coarse|robust...)[_all][_and_none]', where the first
                part specifies the preprocessing step (see `.preprocessing.ReshapeFeatureDistributionsStep.get_all_preprocessors()`) and the second part specifies the features to apply it to and
                finally '_and_none' specifies that the original features should be added back to the features in plain.
                Finally, you can combine all strings without `_all` with `_onehot` to apply one-hot encoding to the categorical
                features specified with `self.fit(..., categorical_features=...)`.
            feature_shift_decoder: ["shuffle", "none", "local_shuffle", "rotate", "auto_rotate"] Whether to shift features for each ensemble configuration.
            normalize_with_test: If True, the test set is used to normalize the data, otherwise the training set is used only.
            average_logits: Whether to average logits or probabilities for ensemble members.
            optimize_metric: The optimization metric to use.
            transformer_predict_kwargs: Additional keyword arguments to pass to the transformer predict method.
            softmax_temperature: A log spaced temperature, it will be applied as logits <- logits/exp(softmax_temperature).
            use_poly_features: Whether to use polynomial features as the last preprocessing step.
            max_poly_features: Maximum number of polynomial features to use, None means unlimited.
            remove_outliers: If not 0.0, will remove outliers from the input features, where values with a standard deviation
                larger than remove_outliers will be removed.
            regression_y_preprocess_transforms: Preprocessing transforms for the target variable. This can be one from `.preprocessing.ReshapeFeatureDistributionsStep.get_all_preprocessors()`, e.g. "power".
                This can also be None to not transform the targets, beside a simple mean/variance normalization.
            add_fingerprint_features: If True, will add one feature of random values, that will be added to
                the input features. This helps discern duplicated samples in the transformer model.
            cancel_nan_borders: Whether to ignore buckets that are tranformed to nan values by inverting a `regression_y_preprocess_transform`.
                This should be set to True, only set this to False if you know what you are doing.
            super_bar_dist_averaging: If we use `regression_y_preprocess_transforms` we need to average the predictions over the different configurations.
                The different configurations all come with different bar_distributions (Riemann distributions), though.
                The default is for us to aggregate all bar distributions using simply scaled borders in the bar distribution, scaled by the mean and std of the target variable.
                If you set this to True, a new bar distribution will be built using all the borders generated in the different configurations.
            subsample_samples: If not None, will use a random subset of the samples for training in each ensemble configuration.
                If 1 or above, this will subsample to the specified number of samples.
                If in 0 to 1, the value is viewed as a fraction of the training set size.
        """

        self.model = model
        self.n_estimators = n_estimators
        self.preprocess_transforms = preprocess_transforms
        self.feature_shift_decoder = feature_shift_decoder
        self.normalize_with_test = normalize_with_test
        self.average_logits = average_logits
        self.optimize_metric = optimize_metric
        self.transformer_predict_kwargs = transformer_predict_kwargs
        self.softmax_temperature = softmax_temperature
        self.use_poly_features = use_poly_features
        self.max_poly_features = max_poly_features
        self.remove_outliers = remove_outliers
        self.regression_y_preprocess_transforms = regression_y_preprocess_transforms
        self.add_fingerprint_features = add_fingerprint_features
        self.cancel_nan_borders = cancel_nan_borders
        self.super_bar_dist_averaging = super_bar_dist_averaging
        self.subsample_samples = subsample_samples

        # check if user is verified
        if config.g_tabpfn_config.user_email and not config.g_tabpfn_config.user_auth_handler.get_user_email_verification_status(config.g_tabpfn_config.user_email):
            raise RuntimeError(
                "Dear User, your email has not been verified. Please, check your mailbox, verify your email and try again!"
            )

    def fit(self, X, y):
        # assert init() is called
        if not config.g_tabpfn_config.is_initialized:
            raise RuntimeError(
                "tabpfn_client.init() must be called before using TabPFNRegressor"
            )

        if config.g_tabpfn_config.use_server:
            try:
                assert (
                    self.model == "latest_tabpfn_hosted"
                ), "Only 'latest_tabpfn_hosted' model is supported at the moment for init(use_server=True)"
            except AssertionError as e:
                print(e)
            config.g_tabpfn_config.inference_handler.fit(X, y)
            self.fitted_ = True
        else:
            raise NotImplementedError(
                "Only server mode is supported at the moment for init(use_server=False)"
            )
        return self

    def predict(self, X):
        full_prediction_dict = self.predict_full(X)
        if self.optimize_metric in ("mse", "rmse", "r2", "mean", None):
            return full_prediction_dict["mean"]
        elif self.optimize_metric in ("mae", "median"):
            return full_prediction_dict["median"]
        elif self.optimize_metric in ("mode", "exact_match"):
            return full_prediction_dict["mode"]
        else:
            raise ValueError(f"Optimize metric {self.optimize_metric} not supported")

    def predict_full(self, X):
        check_is_fitted(self)
        return config.g_tabpfn_config.inference_handler.predict(
            X, task="regression", config=self.get_params()
        )
