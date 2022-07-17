import pytest
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from anndata import AnnData
from ..method_wmean import wmean, run_wmean


def test_wmean():
    m = csr_matrix(np.array([[7., 1., 1., 1.], [4., 2., 1., 2.], [1., 2., 5., 1.], [1., 1., 6., 2.]], dtype=np.float32))
    net = np.array([[1. , 0. ], [2 , 0. ], [0. , -3. ], [0. , 4. ]], dtype=np.float32)
    wmean(m, net, 2, 10000, 42, True)

def test_run_wmean():
    m = np.array([[7., 1., 1., 1.], [4., 2., 1., 2.], [1., 2., 5., 1.], [1., 1., 6., 2.]])
    r = np.array(['S1', 'S2', 'S3', 'S4'])
    c = np.array(['G1', 'G2', 'G3', 'G4'])
    df = pd.DataFrame(m, index=r, columns=c)
    adata = AnnData(df)
    net = pd.DataFrame([['T1', 'G1', 1], ['T1', 'G2', 2], ['T2', 'G3', -3], ['T2', 'G4', 4]],
                   columns=['source', 'target', 'weight'])
    run_wmean(adata, net, verbose=True, use_raw=False, min_n=0, times=2)
