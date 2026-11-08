import os
import re
import joblib
import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report


# ==========================================
# Configuration
# ==========================================

DATASET_PATH = "dataset/labeled_data.csv"
MODEL_DIR = "model"

MODEL_PATH = os.path.join(
    MODEL_DIR,
    "hate_model.pkl"
)

VECTORIZER_PATH = os.path.join(
    MODEL_DIR,
    "vectorizer.pkl"
)


# ==========================================
# Create model folder
# ==========================================

os.makedirs(MODEL_DIR, exist_ok=True)


# ==========================================
# Load Dataset
# ==========================================

print("Loading dataset...")

data = pd.read_csv(DATASET_PATH)

print("\nDataset shape:")
print(data.shape)

print("\nColumns:")
print(data.columns.tolist())


# ==========================================
# Check required columns
# ==========================================

if "tweet" not in data.columns:
    raise ValueError(
        "Dataset must contain a 'tweet' column."
    )

if "class" not in data.columns:
    raise ValueError(
        "Dataset must contain a 'class' column."
    )


# ==========================================
# Text Cleaning
# ==========================================

def clean_text(text):

    text = str(text)

    # Lowercase
    text = text.lower()

    # Remove URLs
    text = re.sub(
        r"http\S+|www\S+",
        " ",
        text
    )

    # Remove mentions
    text = re.sub(
        r"@\w+",
        " ",
        text
    )

    # Remove hashtag symbol
    text = re.sub(
        r"#",
        "",
        text
    )

    # Remove special characters
    text = re.sub(
        r"[^a-zA-Z\s]",
        " ",
        text
    )

    # Remove extra spaces
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ==========================================
# Prepare X
# ==========================================

X = data["tweet"].fillna("")

X = X.apply(clean_text)


# ==========================================
# Prepare Y
# ==========================================

# Standard Kaggle dataset:
#
# class = 0 -> Hate Speech
# class = 1 -> Offensive Language
# class = 2 -> Neither
#
# We convert:
#
# 0 -> Hate Speech = 1
# 1 -> Offensive = 0
# 2 -> Neither = 0

y = data["class"].apply(
    lambda value: 1 if value == 0 else 0
)


# ==========================================
# Display class distribution
# ==========================================

print("\nClass distribution:")

print(
    y.value_counts()
)


# ==========================================
# Train/Test Split
# ==========================================

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.20,
    random_state=42,
    stratify=y
)


print("\nTraining records:", len(X_train))
print("Testing records:", len(X_test))


# ==========================================
# TF-IDF Vectorizer
# ==========================================

print("\nCreating TF-IDF features...")

vectorizer = TfidfVectorizer(
    max_features=10000,
    stop_words="english",
    ngram_range=(1, 2)
)


X_train_tfidf = vectorizer.fit_transform(
    X_train
)

X_test_tfidf = vectorizer.transform(
    X_test
)


print(
    "TF-IDF shape:",
    X_train_tfidf.shape
)


# ==========================================
# Train Logistic Regression
# ==========================================

print("\nTraining model...")

model = LogisticRegression(
    max_iter=1000,
    class_weight="balanced"
)

model.fit(
    X_train_tfidf,
    y_train
)


# ==========================================
# Test Model
# ==========================================

predictions = model.predict(
    X_test_tfidf
)


# ==========================================
# Evaluation
# ==========================================

accuracy = accuracy_score(
    y_test,
    predictions
)

print("\n===================================")
print("MODEL PERFORMANCE")
print("===================================")

print(
    f"Accuracy: {accuracy * 100:.2f}%"
)

print("\nClassification Report:")

print(
    classification_report(
        y_test,
        predictions,
        target_names=[
            "Not Hate Speech",
            "Hate Speech"
        ]
    )
)


# ==========================================
# Save Model
# ==========================================

joblib.dump(
    model,
    MODEL_PATH
)

joblib.dump(
    vectorizer,
    VECTORIZER_PATH
)


print("\n===================================")
print("MODEL SAVED SUCCESSFULLY")
print("===================================")

print(
    f"Model: {MODEL_PATH}"
)

print(
    f"Vectorizer: {VECTORIZER_PATH}"
)