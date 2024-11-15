import scipy.stats as stats
import pandas as pd
from statsmodels.stats.multicomp import pairwise_tukeyhsd
import scikit_posthocs as sp

'''
Statistical tests
'''


def shapiro_wilk_normality_test(df, group_column, values_column, alpha_level = 0.05, verbose = False):
    results = []

    if verbose:
        print('Shapiro-Wilk Normality Test - H0: Samples follow a normal distribution')

    # getting list of groups
    list_groups = list(set(df[group_column]))

    for column in list_groups:
        # p value of the test
        p_shapiro = stats.shapiro(df[df[group_column] == column][values_column].dropna()).pvalue

        # printing results
        if p_shapiro < alpha_level:
            result = 'H0 rejected - non-normal distribution'
        else:
            result = 'H0 cannot be rejected - normal distribution'

        if verbose:
            print('Shapiro-Wilk Normality Test for: {} - p = {:.3f} - Result: {}'.format(column, p_shapiro, result))

        results.append([p_shapiro, result])

    return pd.DataFrame(results, columns=['p_value', 'result'])


def levene_variance_test(df, group_column, values_column, alpha_level = 0.05, center_method = 'mean', verbose = False):
    '''
  Three variations of Levene’s test are possible. The possibilities and their recommended usages are:
    ‘median’ : Recommended for skewed (non-normal) distributions
    ‘mean’ : Recommended for symmetric, moderate-tailed distributions.
    ‘trimmed’ : Recommended for heavy-tailed distributions.
  '''
    # getting list of groups
    list_groups = list(set(df[group_column]))
    list_of_lists = [df[df[group_column] == column][values_column].dropna() for column in list_groups]

    results = []

    if verbose:
        print("Levene's Variance Test - H0: Samples come from populations with equal variances")

    stat_levene, p_levene = stats.levene(*list_of_lists, center=center_method)

    if p_levene < alpha_level:
        result = 'H0 rejected - different variances'
    else:
        result = 'H0 cannot be rejected - same variance'

    if verbose:
        print('Levene Variance Test: p = {:.3f} - Result: {}'.format(p_levene, result))

    results.append([p_levene, result])

    return pd.DataFrame(results, columns=['p_value', 'result'])


def anova(df, group_column, values_column, alpha_level = 0.05, verbose = False):
    # getting list of groups
    list_groups = list(set(df[group_column]))
    list_of_lists = [df[df[group_column] == column][values_column].dropna() for column in list_groups]

    results = []

    # for normal data, One Way ANOVA
    f_anova, p_anova = stats.f_oneway(*list_of_lists)

    if p_anova < alpha_level:
        result = 'H0 rejected -  The average values have statistically significant differences.'
    else:
        result = 'H0 cannot be rejected - The average values have NOT statistically significant differences.'

    if verbose:
        print("ANOVA - H0: Average values are the same")
        print('F statistic = {:5.3f} and probability p = {:5.3f}'.format(f_anova, p_anova))
        print('Result: {}'.format(result))

    results.append([f_anova, p_anova, result])

    return pd.DataFrame(results, columns=['f_statistic', 'p_value', 'result'])


def tukey_test(df, group_column, values_column, alpha_level = 0.05, verbose = False):
    tukey_table = pairwise_tukeyhsd(endog=df[values_column], groups=df[group_column], alpha=alpha_level)
    if verbose:
        print("Tukey's Test - H0: No significant difference has been observed for the pair")
        print(tukey_table.summary())

    return tukey_table


def mood_median_test(df, group_column, values_column, alpha_level = 0.05, verbose = False):
    # getting list of groups
    list_groups = list(set(df[group_column]))
    list_of_lists = [df[df[group_column] == column][values_column].dropna() for column in list_groups]

    results = []

    # for non-normal data, Mood's Median Test
    f_mood, p_mood, med_mood, tbl_mood = stats.median_test(*list_of_lists)

    if p_mood < alpha_level:
        result = 'H0 rejected - The median values have statistically significant differences.'
    else:
        result = 'H0 cannot be rejected - The median values have NOT statistically significant differences.'

    if verbose:
        print("Mood's Median Test - H0: Median values are the same")
        print("F statistic = {:5.3f} and probability p = {:5.3f}".format(f_mood, p_mood))
        print('Result: {}'.format(result))

    results.append([f_mood, p_mood, result])

    return pd.DataFrame(results, columns=['f_statistic', 'p_value', 'result'])


def dunn_test(df, group_column, values_column, alpha_level = 0.05, verbose = False):
    # Dunn's test to check where is the difference
    dunn_results = sp.posthoc_dunn(
        a=df
        , val_col=values_column
        , group_col=group_column
        , p_adjust='bonferroni'
    )

    # clean retults
    list_groups = list(set(df[group_column]))
    results = [[a, b, dunn_results[a][b]] for idx, a in enumerate(list_groups) for b in list_groups[idx + 1:]]

    results = pd.DataFrame(results, columns=['a', 'b', 'p_value'])

    results['reject'] = (results['p_value'] < alpha_level)

    if verbose:
        print("Dunn's Test - H0: No significant difference has been observed for the pair")
        print(results)

    return results


def t_welch_test(df, group_column, values_column, equal_variances = True, alpha_level = 0.05, verbose = False):
    # getting list of groups
    list_groups = list(set(df[group_column]))

    if len(list_groups) == 2:

        results = []

        list_of_lists = [df[df[group_column] == column][values_column].dropna() for column in list_groups]

        # T test for same variance / Welch’s t-test for different variances
        f_ttest, p_ttest = stats.ttest_ind(*list_of_lists, equal_var=equal_variances)

        if p_ttest < alpha_level:
            result = 'H0 rejected - The average values have statistically significant differences.'
        else:
            result = 'H0 cannot be rejected - The average values have NOT statistically significant differences.'

        if verbose:
            print("T-Test / Welch's T-Test - H0: Averages values are the same")
            print("F-statistic = {:5.3f} and p-value = {:5.3f}".format(f_ttest, p_ttest))
            print('Result: {}'.format(result))

        results.append([f_ttest, p_ttest, result])

        return pd.DataFrame(results, columns=['f_statistic', 'p_value', 'result'])

    else:
        print("T-Test / Welch's T-Test: Error: This functions requires exactly 2 groups")


def mann_whitney_u_test(df, group_column, values_column, alpha_level = 0.05, verbose = False):
    # getting list of groups
    list_groups = list(set(df[group_column]))

    if len(list_groups) == 2:

        results = []

        list_of_lists = [df[df[group_column] == column][values_column].dropna() for column in list_groups]

        # performs the test
        stat_mann, p_mann = stats.mannwhitneyu(*list_of_lists)

        if p_mann < alpha_level:
            result = 'H0 rejected - Different distributions.'
        else:
            result = 'H0 cannot be rejected - Same distribution.'

        if verbose:
            print("Mann-Whitney U Test - H0: Same Distributions")
            print("Statistic = {:5.3f} and p-value = {:5.3f}".format(stat_mann, p_mann))
            print('Result: {}'.format(result))

        results.append([stat_mann, p_mann, result])

        return pd.DataFrame(results, columns=['statistic', 'p_value', 'result'])

    else:
        print("Mann-Whitney U Test: Error: This functions requires exactly 2 groups")
