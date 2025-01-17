"""
Method WMEAN.
Code to run the Weighted sum (WMEAN) method.
"""

import numpy as np
import pandas as pd

from .pre import extract, match, rename_net, get_net_mat, filt_min_n
from .method_gsea import std

from anndata import AnnData
from tqdm import tqdm

import numba as nb


@nb.njit(nb.types.UniTuple(nb.f4[:, :], 3)(nb.f4[:, :], nb.f4[:, :], nb.f4[:, :], nb.i8[:], nb.f4[:], nb.i8, nb.i8),
         cache=True)
def run_perm(estimate, mat, net, idxs, div, times, seed):

    mat = np.ascontiguousarray(mat)

    np.random.seed(seed)

    # Init null distirbution
    null_dst = np.zeros((mat.shape[0], net.shape[1], times), dtype=nb.f4)
    pvals = np.zeros((mat.shape[0], net.shape[1]), dtype=nb.f4)

    # Permute
    for i in nb.prange(times):
        np.random.shuffle(idxs)
        null_dst[:, :, i] = mat.dot(net[idxs]) / div
        pvals += np.abs(null_dst[:, :, i]) > np.abs(estimate)

    # Compute empirical p-value
    pvals = np.where(pvals == 0.0, 1.0, pvals).astype(nb.f4)
    pvals = np.where(pvals == times, times-1, pvals).astype(nb.f4)
    pvals = pvals / times
    pvals = np.where(pvals >= 0.5, 1-(pvals), pvals)
    pvals = pvals * 2

    # Compute z-score
    norm = np.zeros((mat.shape[0], net.shape[1]), dtype=nb.f4)
    for i in nb.prange(mat.shape[0]):
        for j in range(net.shape[1]):
            norm[i, j] = (estimate[i, j] - np.mean(null_dst[i, j, :])) / std(null_dst[i, j, :], 1)

    # Compute corr score
    corr = (estimate * -np.log10(pvals)).astype(nb.f4)

    return norm, corr, pvals


def wmean(mat, net, times, batch_size, seed, verbose):

    # Get number of batches
    n_samples = mat.shape[0]
    n_features, n_fsets = net.shape
    n_batches = int(np.ceil(n_samples / batch_size))

    if verbose:
        print('Infering activities on {0} batches.'.format(n_batches))

    # Init empty acts
    estimate = np.zeros((n_samples, n_fsets), dtype=np.float32)
    div = np.sum(np.abs(net), axis=0)
    if times > 1:
        norm = np.zeros((n_samples, n_fsets), dtype=np.float32)
        corr = np.zeros((n_samples, n_fsets), dtype=np.float32)
        pvals = np.zeros((n_samples, n_fsets), dtype=np.float32)
    else:
        norm, corr, pvals = None, None, None

    for i in tqdm(range(n_batches), disable=not verbose):

        # Subset batch
        srt, end = i*batch_size, i*batch_size+batch_size
        tmp = mat[srt:end].A

        # Run WMEAN
        estimate[srt:end] = tmp.dot(net) / div

        if times > 1:
            idxs = np.arange(n_features, dtype=np.int64)
            norm[srt:end], corr[srt:end], pvals[srt:end] = run_perm(estimate[srt:end], tmp, net, idxs, div, times, seed)

    return estimate, norm, corr, pvals


def run_wmean(mat, net, source='source', target='target', weight='weight', times=1000, batch_size=10000, min_n=5, seed=42,
              verbose=False, use_raw=True):
    """
    Weighted sum (WMEAN).

    WMEAN infers regulator activities by performing the weighted sum of the targets and weights, divided by the
    absolute sum of the weights to obtain an enrichment score (`wmean_estimate`). Furthermore, permutations of random
    target features can be performed to obtain a null distribution that can be used to compute a z-score (`wmean_norm`),
    or a corrected estimate (`wmean_corr`) by multiplying `wmean_estimate` by the minus log10 of the obtained empirical
    p-value.

    Parameters
    ----------
    mat : list, DataFrame or AnnData
        List of [features, matrix], dataframe (samples x features) or an AnnData instance.
    net : DataFrame
        Network in long format.
    source : str
        Column name in net with source nodes.
    target : str
        Column name in net with target nodes.
    weight : str
        Column name in net with weights.
    times : int
        How many random permutations to do.
    batch_size : int
        Size of the batches to use. Increasing this will consume more memmory but it will run faster.
    min_n : int
        Minimum of targets per source. If less, sources are removed.
    seed : int
        Random seed to use.
    verbose : bool
        Whether to show progress.
    use_raw : bool
        Use raw attribute of mat if present.

    Returns
    -------
    estimate : DataFrame
        WMEAN scores. Stored in `.obsm['wmean_estimate']` if `mat` is AnnData.
    norm : DataFrame
        Normalized WMEAN scores. Stored in `.obsm['wmean_norm']` if `mat` is AnnData.
    corr : DataFrame
        Corrected WMEAN scores. Stored in `.obsm['wmean_corr']` if `mat` is AnnData.
    pvals : DataFrame
        Obtained p-values. Stored in `.obsm['wmean_pvals']` if `mat` is AnnData.
    """

    # Extract sparse matrix and array of genes
    m, r, c = extract(mat, use_raw=use_raw, verbose=verbose)

    # Transform net
    net = rename_net(net, source=source, target=target, weight=weight)
    net = filt_min_n(c, net, min_n=min_n)
    sources, targets, net = get_net_mat(net)

    # Match arrays
    net = match(c, targets, net)

    if verbose:
        print('Running wmean on mat with {0} samples and {1} targets for {2} sources.'.format(m.shape[0], len(c),
                                                                                              net.shape[1]))

    # Run WMEAN
    estimate, norm, corr, pvals = wmean(m, net, times, batch_size, seed, verbose)

    # Transform to df
    estimate = pd.DataFrame(estimate, index=r, columns=sources)
    estimate.name = 'wmean_estimate'
    if pvals is not None:
        norm = pd.DataFrame(norm, index=r, columns=sources)
        norm.name = 'wmean_norm'
        corr = pd.DataFrame(corr, index=r, columns=sources)
        corr.name = 'wmean_corr'
        pvals = pd.DataFrame(pvals, index=r, columns=sources)
        pvals.name = 'wmean_pvals'

    # AnnData support
    if isinstance(mat, AnnData):
        # Update obsm AnnData object
        mat.obsm[estimate.name] = estimate
        if pvals is not None:
            mat.obsm[norm.name] = norm
            mat.obsm[corr.name] = corr
            mat.obsm[pvals.name] = pvals
    else:
        if pvals is not None:
            return estimate, norm, corr, pvals
        else:
            return estimate
