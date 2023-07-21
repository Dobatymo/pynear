import time
import numpy as np
import pandas as pd
import faiss
import pyvptree
from typing import Callable, Any, List, Tuple, Union
from dataclasses import dataclass
from pyvptree.benchmark.dataset import BenchmarkDataset
from pyvptree.logging import create_and_configure_log

logger = create_and_configure_log(__name__)

@dataclass
class FaissComparatorBenchmarkCase:
    # list of test case K values (how many neighbors to search)
    # each case will result in multiple tests, one for each k value
    ks: List[int]

    # the data to use in the test case
    dataset: BenchmarkDataset

    # the random seed for reproducibility
    seed: int = 12246

    def __str__(self):
        return f"{self.dataset.name()}-k={self.ks}"

class FaissComparatorBenchmark:

    """
    A generic benchmark build helper class to automate benchmark generation.
    """

    def __init__(self, benchmark_cases: List[FaissComparatorBenchmarkCase]):
        """
        Build a benchmark comparator between pyvptree and faiss.

        Args:
            benchmark_cases (List[BenchmarkCase]): the list of benchmark cases to perform.
        """
        self._benchmark_cases = benchmark_cases
        self._results = pd.DataFrame()

    def run(self):

        num_cases = len(self._benchmark_cases)
        logger.info(f"start running benchmark for {num_cases} cases ...")

        results = []
        for case in self._benchmark_cases:

            start_case = time.time()
            logger.info(f"starting case {str(case)} ...")
            logger.info("splittting dataset into train / test... ")
            train, test = self._split_test_train_case(case.dataset)
            logger.info(f"split sizes test = {test.shape[0]}, train = {train.shape[0]}... ")

            start = time.time()
            logger.info("generating faiss index ... ")
            faiss_index = self._generate_faiss_index(train, case.dataset._pyvpindex_type)
            logger.info(f"done, faiss index took {time.time()-start:0.3f} seconds... ")

            start = time.time()
            logger.info("generating pyvp index ... ")
            pyvptree_index = self._generate_pyvptree_index(train, case.dataset._pyvpindex_type)
            logger.info(f"done, pyvptree index took {time.time()-start:0.3f} seconds... ")
            for k in case.ks:

                logger.info("searching into faiss index ... ")
                start = time.time()
                self._search_knn_faiss(faiss_index, test, k)
                end = time.time()
                faiss_time = end-start
                logger.info(f"faiss search for k = {k} took {faiss_time:0.3f} seconds... ")

                logger.info("searching into pyvptree index ... ")
                start = time.time()
                self._search_knn_pyvptree(pyvptree_index, test, k)
                end = time.time()
                pyvptree_time = end-start
                logger.info(f"pyvptree search for k = {k} took {pyvptree_time:0.3f} seconds... ")

                # faiss query
                results.append({
                    "k": k,
                    "dimension": case.dataset.dimension(),
                    "size": case.dataset.size(),
                    "query_size": test.shape[0],
                    "faiss_time": faiss_time,
                    "pyvptree_time": pyvptree_time
                })

            # make sure dataset is unloaded to prevent memory overflow
            logger.info(f"case took {time.time()-start_case:0.3f}")
            case.dataset.unload_data()

        self._results = pd.DataFrame(results)

    def result(self) -> pd.DataFrame:
        return self._results

    def _split_test_train_case(self, dataset: BenchmarkDataset):

        n_test = 16 # perform 16 queries for test and rest for train
        data: np.ndarray = dataset.data()
        np.random.shuffle(data)
        n = dataset.size()
        n_train = n - n_test
        return data[0:n_train,:], data[n_train:,:] 
        
    def _generate_faiss_index(self, features: np.ndarray, index_type: Any):

        d = features.shape[1]
        faiss_index = faiss.IndexFlatL2(d) 
        if index_type == pyvptree.VPTreeBinaryIndex:
            d = features.shape[1] * 8
            quantizer = faiss.IndexBinaryFlat(d)

            # Number of clusters.
            nlist = int(np.sqrt(features.shape[0]))

            faiss_index = faiss.IndexBinaryIVF(quantizer, d, nlist)
            faiss_index.nprobe = d  # Number of nearest clusters to be searched per query.
            faiss_index.train(features.shape[0], features)

        faiss_index.add(features)
        return faiss_index

    def _generate_pyvptree_index(self, features: np.ndarray, index_type: Any):
        vptree_index = pyvptree.VPTreeL2Index()
        if index_type == pyvptree.VPTreeBinaryIndex:
            vptree_index = pyvptree.VPTreeBinaryIndex()
        vptree_index.set(features)
        return vptree_index


    def _search_knn_faiss(self, index, query_features, k=1):
        return index.search(query_features, k=k)

    def _search_knn_pyvptree(self, index, query_features, k=1):
        return index.searchKNN(query_features, k)
