import hashlib
import os
import time
from enum import Enum
from typing import List, Dict, Tuple, Optional

import joblib
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.linear_model import SGDClassifier
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.multioutput import MultiOutputClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import LabelEncoder, MultiLabelBinarizer, OneHotEncoder
from sklearn.svm import LinearSVC

from services.test_service import select_random_issues_from_train_issues_to_test_inference


class SupportedModels(Enum):
    RANDOM_FOREST = "random_forest"
    LOGISTIC = "logistic"
    MLP  = "mlp"
    SGD = "sgd"
    GRADIENT_BOOSTING = "gbt" # Relatively slow.
    LINEAR_SVC = "svm"


class JiraLabelInference:
    """Train and run Jira field classifiers with shared semantic features."""

    EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
    RANDOM_STATE = 42
    _bert_model = None
    _embedding_cache: Dict[str, np.ndarray] = {}

    @classmethod
    def _get_bert_model(cls):
        if cls._bert_model is None:
            cls._bert_model = SentenceTransformer(cls.EMBEDDING_MODEL_NAME)
        return cls._bert_model
    def __init__(self,
                 model_type: str = "logistic",
                 multi_label: bool = True,
                 structured_fields: Optional[List[str]] = None,
                 model_path: Optional[str] = None,
                 test_rand_seed=1
                 ):
        """
        Args:
            model_type: "logistic" or "random_forest"
            multi_label: If True → multi-label, else single-label classification
            structured_fields: list of categorical fields to use (e.g., ["issue_type", "component"])
            model_path: Path to save/load trained model
        """
        self.model_type = model_type
        self.multi_label = multi_label
        self.structured_fields = [field for field in (structured_fields or []) if field]
        # self.model_dir = "ml_models"
        self.model_dir = f"ml_models/{model_type}"
        os.makedirs(self.model_dir, exist_ok=True)
        self.model_path = f"{self.model_dir}/{model_path}" if model_path else None

        # Models
        self.model = None

        # Encoders
        self.label_encoder = None
        self.mlb = None
        self.oh_encoder = None  # for structured categorical fields
        self.test_data = []
        self.test_rand_seed = test_rand_seed
        self.label_centroids = {}

    # -------- Feature Extraction --------
    def extract_text_features(self, issues: List[Dict]) -> np.ndarray:
        """Return normalised MiniLM embeddings, reusing them across classifiers."""
        texts = [f"{i.get('summary', '')} {i.get('description', '')}" for i in issues]
        if not texts:
            return np.empty((0, 0), dtype=np.float32)

        keys = [hashlib.sha256(text.encode("utf-8")).hexdigest() for text in texts]
        missing_indexes = [
            idx for idx, key in enumerate(keys)
            if key not in self._embedding_cache
        ]
        if missing_indexes:
            missing_texts = [texts[idx] for idx in missing_indexes]
            encoded = self._get_bert_model().encode(
                missing_texts,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            for idx, vector in zip(missing_indexes, encoded):
                self._embedding_cache[keys[idx]] = np.asarray(
                    vector, dtype=np.float32
                )

        return np.vstack([self._embedding_cache[key] for key in keys])

    def extract_structured_features(self, issues: List[Dict], fit: bool = False) -> np.ndarray:
        if not self.structured_fields:
            return np.zeros((len(issues), 0))  # no extra features

        data = []
        for issue in issues:
            row = [issue.get(field, "UNK") for field in self.structured_fields]
            data.append(row)

        if fit or (self.oh_encoder is None):
            # self.oh_encoder = OneHotEncoder(handle_unknown="ignore", sparse=False)
            import sklearn
            if int(sklearn.__version__.split(".")[1]) >= 2:  # sklearn >= 1.2
                self.oh_encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
            else:
                self.oh_encoder = OneHotEncoder(handle_unknown="ignore", sparse=False)
            struct_features = self.oh_encoder.fit_transform(data)
        else:
            struct_features = self.oh_encoder.transform(data)

        return struct_features

    def extract_features(self, issues: List[Dict], fit: bool = False) -> np.ndarray:
        X_text = self.extract_text_features(issues)
        X_struct = self.extract_structured_features(issues, fit=fit)
        return np.hstack([X_text, X_struct]) if X_struct.shape[1] > 0 else X_text

    # -------- Model Setup --------
    def _init_model(self):
        if self.model_type == "random_forest":
            base = RandomForestClassifier(
                n_estimators=300,
                class_weight="balanced_subsample",
                n_jobs=-1,
                random_state=self.RANDOM_STATE,
            )
        elif self.model_type == "logistic":
            base = LogisticRegression(
                max_iter=2000,
                class_weight="balanced",
                random_state=self.RANDOM_STATE,
            )
        elif self.model_type == "mlp":
            base = MLPClassifier(
                hidden_layer_sizes=(256, 128),
                max_iter=1000,
                early_stopping=True,
                n_iter_no_change=20,
                random_state=self.RANDOM_STATE,
            )
        elif self.model_type == "gbt":
            base = GradientBoostingClassifier(
                n_estimators=200,
                random_state=self.RANDOM_STATE,
            )
        elif self.model_type == "svm":
            base = CalibratedClassifierCV(
                LinearSVC(
                    class_weight="balanced",
                    random_state=self.RANDOM_STATE,
                ),
                method="sigmoid",
                cv=2,
            )
        elif self.model_type == "sgd":
            base = SGDClassifier(
                loss="log_loss",
                class_weight="balanced",
                max_iter=2000,
                tol=1e-3,
                random_state=self.RANDOM_STATE,
            )
        else:
            raise ValueError(f"Unsupported model_type: {self.model_type}")

        if self.multi_label:
            return MultiOutputClassifier(base)
        return base

    # -------- Training --------
    def train(self,
              jira_issues: List[Dict],
              target_field: str = "labels",
              is_test=True,
              issues_to_exclude=None
              ):
        # labeled = [i for i in jira_issues if i.get(target_field)]
        labeled = [i for i in jira_issues if target_field in i and i[target_field]]
        if not labeled:
            raise ValueError("No labeled issues provided for training.")

        # Add Random Tests
        if is_test:
            self.test_data = select_random_issues_from_train_issues_to_test_inference(
                labeled,
                target_field,
                test_issues_percentage=0.2,
                test_rand_seed=self.test_rand_seed,
                issues_to_exclude=issues_to_exclude  # [("issuetype", "Epic")]
            )
            # print(f"[DEBUG] test_seed: {test_rand_seed}")
            # print(f"[DEBUG] test_issue_keys: {list(map(lambda x: x['key'], self.test_data))}")

            # Exclude Test data from Training data
            test_data_keys = list(map(lambda x: x["key"], self.test_data))
            labeled = list(filter(lambda x: x["key"] not in test_data_keys, labeled))

        X = self.extract_features(labeled, fit=True)

        if self.multi_label:
            y = [i[target_field] for i in labeled]
            self.mlb = MultiLabelBinarizer()
            y_encoded = self.mlb.fit_transform(y)
        else:
            y = [i[target_field][0] if isinstance(i[target_field], list) else i[target_field]
                 for i in labeled]
            self.label_encoder = LabelEncoder()
            y_encoded = self.label_encoder.fit_transform(y)

        self.model = self._init_model()
        # DEBUG
        # print("[DEBUG] np.unique(y_encoded):", np.unique(y_encoded))
        try:
            self.model.fit(X, y_encoded)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to train model '{self.model_type}' "
                f"for field '{target_field}'"
            ) from exc

        # --- Compute label centroids (for interpretability) ---
        if self.multi_label and hasattr(self, "mlb"):
            self.label_centroids = {}
            X_labeled = self.extract_features(labeled, fit=False)
            y_encoded = self.mlb.transform([i[target_field] for i in labeled])

            for idx, label in enumerate(self.mlb.classes_):
                label_indices = np.where(y_encoded[:, idx] == 1)[0]
                if len(label_indices) > 0:
                    self.label_centroids[label] = np.mean(X_labeled[label_indices], axis=0)

        if self.model_path:
            self.save_model()

    # -------- Prediction --------
    def get_top_influential_terms(self, text: str, predicted_labels: List[str], top_n: int = 5) -> List[str]:
        """Return the most semantically influential words/phrases for predicted labels."""
        if not getattr(self, "label_centroids", None):
            return []

        tokens = [t for t in text.split() if len(t) > 2]
        if not tokens:
            return []

        # Encode token embeddings (text-only)
        token_embs = self._get_bert_model().encode(tokens, normalize_embeddings=True, show_progress_bar=False)
        emb_dim = token_embs.shape[1]

        influential_terms = []

        for label in predicted_labels:
            if label not in self.label_centroids:
                continue

            label_vec = self.label_centroids[label]

            # Handle centroid vectors with extra structured dimensions
            if label_vec.shape[0] > emb_dim:
                label_vec = label_vec[:emb_dim]
            elif label_vec.shape[0] < emb_dim:
                label_vec = np.pad(label_vec, (0, emb_dim - label_vec.shape[0]))

            label_vec = label_vec.reshape(1, -1)

            # Compute similarity
            sims = cosine_similarity(token_embs, label_vec).flatten()
            top_indices = sims.argsort()[-top_n:][::-1]
            top_words = [tokens[i] for i in top_indices]
            influential_terms.extend(top_words)

        # Remove duplicates, keep order
        return list(dict.fromkeys(influential_terms))[:top_n]

    def predict(self,
                jira_issues: List[Dict],
                target_field: str = "labels",
                threshold: float = 0.5,
                issues_to_exclude = None  # [("issuetype", "Epic")]
                ) -> List[Tuple[str, List[str], float]]:
        if not self.model:
            if self.model_path and os.path.exists(self.model_path):
                self.load_model()
            else:
                raise ValueError("Model not trained or loaded.")

        # unlabeled = [i for i in jira_issues if not i.get(target_field)]
        unlabeled = [i for i in jira_issues if target_field in i and not i[target_field]]
        if not unlabeled:
            return []

        # exclude if needed (e.g: no need to predict epic link for issues of type Epic)
        if issues_to_exclude:
            for couple in issues_to_exclude:
                key, val = couple
                unlabeled = list(filter(lambda x: x[key] != val, unlabeled))

        # Inject test data if any
        unlabeled.extend(self.test_data)

        X_unlabeled = self.extract_features(unlabeled, fit=False)
        predictions = []

        if self.multi_label:
            # Get probability matrix correctly (n_samples, n_labels)
            # y_pred_proba = self.model.predict_proba(X_unlabeled)
            # prob_matrix = np.vstack([col[:, 1] for col in y_pred_proba]).T
            y_pred_proba, prob_matrix = self.get_pred_proba(X_unlabeled)

            for issue, probs in zip(unlabeled, prob_matrix):
                selected = probs > threshold
                predicted_labels = self.mlb.classes_[selected]
                confidence = round(np.mean(probs[selected]), 3) if predicted_labels.size > 0 else 0.0
                # predictions.append((issue["key"], predicted_labels.tolist(), confidence))
                # Combine summary + description for interpretability
                text = f"{issue.get('summary', '')} {issue.get('description', '')}"
                influential_terms = []  #self.get_top_influential_terms(text, predicted_labels)
                predictions.append((issue["key"], predicted_labels.tolist(), confidence, influential_terms))
        else:
            y_pred = self.model.predict(X_unlabeled)
            if hasattr(self.model, "predict_proba"):
                y_proba = self.model.predict_proba(X_unlabeled)
                confidences = np.max(y_proba, axis=1)
            else:
                print(f"[DEBUG] model {self.model_type} has no attr predict_proba")
                confidences = [1.0] * len(y_pred)

            decoded = self.label_encoder.inverse_transform(y_pred)
            for issue, label, conf in zip(unlabeled, decoded, confidences):
                # predictions.append((issue["key"], [label], float(round(conf, 3))))
                # predictions.append((issue["key"], label, float(round(conf, 3))))
                text = f"{issue.get('summary', '')} {issue.get('description', '')}"
                influential_terms = []  #self.get_top_influential_terms(text, label)
                predictions.append((issue["key"], label.tolist(), float(round(conf, 3)), influential_terms))

        return predictions

    # -------- Save / Load --------
    def save_model(self):
        save_dict = {
            "model": self.model,
            "multi_label": self.multi_label,
            "label_encoder": self.label_encoder,
            "mlb": self.mlb,
            "oh_encoder": self.oh_encoder,
            "structured_fields": self.structured_fields
        }
        joblib.dump(save_dict, self.model_path)

    def load_model(self):
        obj = joblib.load(self.model_path)
        self.model = obj["model"]
        self.multi_label = obj["multi_label"]
        self.label_encoder = obj["label_encoder"]
        self.mlb = obj["mlb"]
        self.oh_encoder = obj["oh_encoder"]
        self.structured_fields = obj["structured_fields"]

    # Linear SVC quick fix
    # import numpy as np
    def get_pred_proba(self, X_unlabeled):
        """
        Get probability predictions for unlabeled samples, safely handling
        MultiOutputClassifier and base estimators with or without predict_proba().

        Returns:
            (y_pred_proba, prob_matrix)
            - y_pred_proba: raw list of arrays from underlying estimators
            - prob_matrix: np.ndarray of shape (n_samples, n_labels)
        """
        model = self.model

        # --- Case 1: MultiOutputClassifier ---
        if hasattr(model, "estimators_"):
            y_pred_proba = []
            for est in model.estimators_:
                # Prefer predict_proba
                if hasattr(est, "predict_proba"):
                    probs = est.predict_proba(X_unlabeled)
                    # Take positive class probability if 2D
                    if probs.ndim == 2 and probs.shape[1] > 1:
                        probs = probs[:, 1]
                # Fall back to decision_function
                elif hasattr(est, "decision_function"):
                    df = est.decision_function(X_unlabeled)
                    probs = 1 / (1 + np.exp(-df))  # sigmoid
                # Final fallback: predict
                else:
                    preds = est.predict(X_unlabeled)
                    probs = preds.astype(float)

                y_pred_proba.append(probs)

            # Convert to matrix shape (n_samples, n_labels)
            prob_matrix = np.array(y_pred_proba).T

        # --- Case 2: Single-output model ---
        else:
            if hasattr(model, "predict_proba"):
                probs = model.predict_proba(X_unlabeled)
                # If 2D (e.g., [p0, p1]), take positive class probability
                if probs.ndim == 2 and probs.shape[1] > 1:
                    probs = probs[:, 1]
            elif hasattr(model, "decision_function"):
                df = model.decision_function(X_unlabeled)
                probs = 1 / (1 + np.exp(-df))
            else:
                preds = model.predict(X_unlabeled)
                probs = preds.astype(float)

            y_pred_proba = [probs]
            prob_matrix = np.array(probs).reshape(-1, 1)

        # --- Ensure matrix aligns with label count ---
        n_labels = len(getattr(self, "mlb", {}).classes_) if hasattr(self, "mlb") else None
        if n_labels and prob_matrix.shape[1] != n_labels:
            # Transpose if likely flipped
            if prob_matrix.shape[0] == n_labels:
                prob_matrix = prob_matrix.T
            # Or pad/truncate if mismatched (defensive)
            elif prob_matrix.shape[1] > n_labels:
                prob_matrix = prob_matrix[:, :n_labels]
            elif prob_matrix.shape[1] < n_labels:
                prob_matrix = np.pad(prob_matrix, ((0, 0), (0, n_labels - prob_matrix.shape[1])))

        return y_pred_proba, prob_matrix


def compute_accuracy(target_field, test_data, predictions):
    """Compute exact holdout accuracy (no substring matching)."""
    from ml.metrics import as_label_set

    pass_count = 0
    confidence_sum = 0.0
    test_status_dict = {}
    for test in test_data:
        key = test["key"]
        cur_prediction = next(
            (item for item in predictions if item[0] == key), None
        )
        predicted_value = cur_prediction[1] if cur_prediction else None
        expected_value = test[target_field]

        if isinstance(expected_value, (list, tuple, set)) or isinstance(
            predicted_value, (list, tuple, set)
        ):
            is_pass = as_label_set(expected_value) == as_label_set(
                predicted_value
            )
        else:
            is_pass = (
                str(expected_value).strip()
                == str(predicted_value).strip()
            )

        pass_count += int(is_pass)
        confidence = float(cur_prediction[2]) if cur_prediction else 0.0
        confidence_sum += confidence
        test_status_dict[key] = {
            "expected": expected_value,
            "predicted": predicted_value,
            "confidence": confidence,
        }

    denominator = len(test_data) or 1
    return (
        pass_count / denominator,
        confidence_sum / denominator,
        test_status_dict,
    )

def infer_using_model(
        jira_issues,
        model_type="mlp",
        target_field="labels",
        structured_fields=None,
        is_test=False,
        test_rand_seed=None,
        issues_to_exclude=None
):
    # good_predictions_per_model[model_type] = []
    start_time = time.perf_counter()
    # is_multi_label = target_field in ["components", "labels"]
    is_multi_label = False
    # is_structured_fields = len(structured_fields) > 0
    # sf_str = "_sf" if is_structured_fields else ""
    sf_str = "_".join(structured_fields) if structured_fields else ""
    sf_str = f"_{sf_str}" if sf_str else ""
    # model_path = f"jira_model_{target_field}_{model_type}{sf_str}.pkl"
    model_path = f"{target_field.replace(' ', '')}{sf_str}.pkl"
    print("[DEBUG] model_path:", model_path)

    # Train multi-label model
    clf = JiraLabelInference(
        model_type=model_type,
        multi_label=is_multi_label,
        structured_fields=structured_fields,
        model_path=model_path,
        test_rand_seed=test_rand_seed
    )
    clf.train(jira_issues, target_field=target_field, is_test=is_test, issues_to_exclude=issues_to_exclude)

    # Predict for unlabeled issues
    all_preds = clf.predict(jira_issues, target_field=target_field, issues_to_exclude=issues_to_exclude)

    end_time = time.perf_counter()
    elapsed_time = end_time - start_time

    # Exclude test data if any
    test_data_keys = list(map(lambda x: x["key"], clf.test_data))
    preds = list(filter(lambda x: x[0] not in test_data_keys, all_preds))

    return all_preds, preds, elapsed_time, clf.test_data if is_test else all_preds


# if __name__ == "__main__":
def my_main():
    pass
