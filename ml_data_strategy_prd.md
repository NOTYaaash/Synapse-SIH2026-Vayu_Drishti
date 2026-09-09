# Product Requirements Document (PRD): ML Data Strategy & Bias Mitigation

## 1. Executive Summary
**Objective**: Optimize the training dataset size and mitigate positive class bias (false positives) in the Convolutional Neural Network (CNN) cyclone intensity predictor.
**Context**: The current model, trained on a limited subset (1k files) of positive cyclone observations, suffers from severe positive bias, predicting a 17kt depression (false positive) on non-cyclonic satellite frames. Furthermore, downloading the entire historical NASA GPM IMERG dataset (4.87 lakh `.nc4` files) is computationally and temporally infeasible.
**Solution**: Implement a targeted, cross-referenced data ingestion pipeline combining IBTrACS temporal filters (to extract exactly ~10k positive samples) and explicit Negative Mining (to teach the model the null state).

## 2. Problem Definition
### 2.1. Infeasible Dataset Scale
The raw NASA Earthdata repository contains ~487,000 files (30-minute intervals over ~24 years). Downloading this entire corpus requires extreme bandwidth and storage, most of which represents "empty ocean" or standard meteorological noise.

### 2.2. Positive Class Bias (Hallucinations)
The model currently exhibits a `False Positive Rate (FPR)` approaching 100% on clear-weather inferences. 
*   **Root Cause**: The neural network weights were optimized exclusively on tensors containing structural cyclone features (spiral bands, tight pressure gradients). 
*   **Mathematical Implication**: The model's latent space lacks a representation of the "null class" (0kt). Therefore, any input tensor is mapped to the lowest known value in its training distribution (e.g., a 17kt depression), failing to regress to zero.

## 3. Technical Requirements & Implementation Strategy

### 3.1. Targeted Positive Sampling (Temporal Intersection)
We will leverage the existing spatial-temporal mapping script (`ml_engine/pipelines/download_nasa_gpm.py`) to algorithmically filter the 487k files down to the ~10k highly relevant frames.

*   **Filter Logic**:
    1. Parse `ibtracs.ALL.list.v04r01.csv` for observations in the NIO (North Indian Ocean) basins (`NI`, `BB`, `AS`).
    2. Extract the ISO timestamps for each recorded cyclone observation.
    3. Apply a padding window (`pad_hours = 6`) to capture cyclogenesis (formation) and dissipation phases.
    4. Perform an intersection against the NASA Earthdata URL manifest.
*   **Expected Yield**: This will isolate ~10,000 to 15,000 `.nc4` files. This is a statistically significant sample size for training a ResNet/VGG-style architecture without requiring transfer learning from ImageNet, provided data augmentation is utilized.

### 3.2. Explicit Negative Mining (The "Null" Class)
To correct the model's regression bounds, we must inject targeted negative variance.

*   **Sampling Methodology**:
    *   Randomly sample ~2,000 to 3,000 `.nc4` URLs from the NASA manifest that **do not** intersect with any IBTrACS active windows.
    *   Ensure seasonal stratification (sample non-cyclone frames during Monsoon and Pre-Monsoon seasons to teach the model to differentiate between standard monsoonal cloud cover and organized cyclonic convection).
*   **Labeling Protocol**:
    *   Assign a continuous wind speed target of `0.0` (knots).
    *   Assign a discrete classification target of `0` (Non-cyclonic).

### 3.3. Data Augmentation Pipeline
To maximize the feature variance of the 10k positive samples and prevent overfitting:
*   **Geospatial Flipping**: Horizontal flips for Southern Hemisphere storms (to standardize the Coriolis-induced rotation).
*   **Rotational Invariance**: Apply random rotations ($0^\circ, 90^\circ, 180^\circ, 270^\circ$) during the `DataLoader` phase. (Cyclones exhibit structural symmetry that is rotationally invariant).

## 4. Verification & Acceptance Criteria
> [!IMPORTANT]
> The updated model must pass the following validation checks before deployment.

1.  **Dataset Size**: Total downloaded payload must not exceed ~15,000 files.
2.  **Zero-State Inference**: When fed an array of `np.full((128,128), 290.0)` (standard clear-weather TIR-1 temp) or actual non-cyclone `.nc4` data, the model's regression head must output `< 15 knots`, and the classification head must predict `Category 0`.
3.  **Recall Maintenance**: The negative sampling injection must not degrade the recall accuracy for actual Severe Cyclones (Orange/Red alerts).
