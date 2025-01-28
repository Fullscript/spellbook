The stats_magic module provides a suite of statistical tests and tools for analyzing datasets. It simplifies the process of conducting normality tests, variance analysis, ANOVA, and various other statistical methods. The module supports multi-group comparisons as well as two-group analyses, making it ideal for exploratory data analysis and hypothesis testing.

### Key Features

1. **Comprehensive Statistical Tests:**
  * Covers normality, variance, mean, and median comparisons.
  * Includes both parametric and non-parametric methods.
2. **Multi-Group Analysis:**
  * Tools like ANOVA, Tukey’s, and Dunn’s tests for multi-level datasets.
3. **Two-Group Analysis:**
  * Student’s t-test, Welch’s t-test, and Mann-Whitney U test for pairwise comparisons.
4. **Detailed Outputs:**
  * Returns results as Pandas DataFrames for easy analysis.
  * Supports verbose mode for detailed explanations of results.

# Setup

## Import the Module
To begin using stats_magic, import it into your Python environment.
```python
from spellbook import stats_magic
```

### Multi-Level Tests

These tests are designed for datasets with more than two groups, allowing comparisons across multiple categories.

1. **Shapiro-Wilk Normality Test**

Tests if the data in each group follows a normal distribution.
```python
shapiro_df = stats_magic.shapiro_wilk_normality_test(
    df=df_penguins,
    group_column='species',
    values_column='flipper_length_mm',
    alpha_level=0.05,
    verbose=True
)
```
Key Parameters:
* `group_column`: The column defining groups (e.g., species).
* `values_column`: The column containing numeric values to test.
* `alpha_level`: Significance level (default 0.05).
* `verbose`: Print detailed output (default False).

2. **Levene’s Variance Test**

Tests if the variances across groups are equal.
```python
levene_df = stats_magic.levene_variance_test(
    df=df_penguins,
    group_column='species',
    values_column='flipper_length_mm',
    alpha_level=0.05,
    center_method='mean',
    verbose=True
)
```
Key Parameters:
* `center_method`: Method to calculate central tendency (mean, median, or trimmed).

3. **ANOVA**

Performs an analysis of variance to test if means across groups are significantly different.
```python
anova_df = stats_magic.anova(
    df=df_penguins,
    group_column='species',
    values_column='flipper_length_mm',
    alpha_level=0.05,
    verbose=True
)
```

4. **Tukey’s Test**

Conducts pairwise comparisons between group means.
```python
tukey_test_df = stats_magic.tukey_test(
    df=df_penguins,
    group_column='species',
    values_column='flipper_length_mm',
    alpha_level=0.05,
    verbose=True
)
```

5. **Mood’s Median Test**

Tests if the medians across groups are significantly different.
```python
mood_median_test_df = stats_magic.mood_median_test(
    df=df_penguins,
    group_column='species',
    values_column='flipper_length_mm',
    alpha_level=0.05,
    verbose=True
)
```

6. **Dunn’s Test**

Performs pairwise comparisons between groups, adjusting p-values to account for multiple tests.
```python
dunn_test_df = stats_magic.dunn_test(
    df=df_penguins,
    group_column='species',
    values_column='flipper_length_mm',
    alpha_level=0.05,
    verbose=True
)
```

### Two-Level Tests

These tests are designed for datasets with exactly two groups, allowing direct comparisons between them.

**Setup: Create a Two-Group Dataset**
Filter the dataset to include only two groups.

```python
two_group_df = df_penguins[
    (df_penguins['species'] == 'Adelie') | (df_penguins['species'] == 'Gentoo')
]
```

1. **Student’s t-test / Welch’s t-test**

Tests if the means of two groups are significantly different.
```python
t_welch_test_df = stats_magic.t_welch_test(
    df=two_group_df,
    group_column='species',
    values_column='flipper_length_mm',
    equal_variances=True,
    alpha_level=0.05,
    verbose=True
)
```
Key Parameters:
* `equal_variances`: Set to False to use Welch’s t-test for unequal variances.

2. **Mann-Whitney U Test**

Tests if the distributions of two groups are significantly different.
```python
mann_whitney_u_test_df = stats_magic.mann_whitney_u_test(
    df=two_group_df,
    group_column='species',
    values_column='flipper_length_mm',
    alpha_level=0.05,
    verbose=True
)
```