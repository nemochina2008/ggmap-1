import tempfile
import shutil
import subprocess
import sys
import hashlib
import os
import pickle
from io import StringIO
import collections
import datetime
import time

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from skbio.stats.distance import DistanceMatrix
from skbio.tree import TreeNode

from ggmap.snippets import (pandas2biom, cluster_run, biom2pandas,
                            _add_timing_cmds)


plt.switch_backend('Agg')
plt.rc('font', family='DejaVu Sans')

FILE_REFERENCE_TREE = None
QIIME_ENV = 'qiime_env'


def _get_ref_phylogeny(file_tree=None, env=QIIME_ENV):
    """Use QIIME config to infer location of reference tree or pass given tree.

    Parameters
    ----------
    file_tree : str
        Default: None.
        If None is set, than we need to activate qiime environment, print
        config and search for the rigth path information.
        Otherwise, specified reference tree is returned without doing anything.
    env : str
        Default: global constant QIIME_ENV value.
        Conda environment name for QIIME.

    Returns
    -------
    Filepath to reference tree.
    """
    global FILE_REFERENCE_TREE
    if file_tree is not None:
        return file_tree
    if FILE_REFERENCE_TREE is None:
        err = StringIO()
        with subprocess.Popen(("source activate %s && "
                               "print_qiime_config.py "
                               "| grep 'pick_otus_reference_seqs_fp:'" %
                               env),
                              shell=True,
                              stdout=subprocess.PIPE,
                              executable="bash") as call_x:
            out, err = call_x.communicate()
            if (call_x.wait() != 0):
                raise ValueError("_get_ref_phylogeny(): something went wrong")

            # convert from b'' to string
            out = out.decode()
            # split key:\tvalue
            out = out.split('\t')[1]
            # remove trailing \n
            out = out.rstrip()
            # chop '/rep_set/97_otus.fasta' from found path
            out = '/'.join(out.split('/')[:-2])
            FILE_REFERENCE_TREE = out + '/trees/97_otus.tree'
    return FILE_REFERENCE_TREE


def _getremaining(counts_sums):
    """Compute number of samples that have at least X read counts.

    Parameters
    ----------
    counts_sum : Pandas.Series
        Reads per sample.

    Returns
    -------
    Pandas.Series:
        Index = sequencing depths,
        Values = number samples with at least this sequencing depth.
    """
    d = dict()
    remaining = counts_sums.shape[0]
    numdepths = counts_sums.value_counts().sort_index()
    for depth, numsamples in numdepths.iteritems():
        d[depth] = remaining
        remaining -= numsamples
    return pd.Series(data=d, name='remaining').to_frame()


def _parse_alpha_div_collated(filename, metric=None):
    """Parse QIIME's alpha_div_collated file for plotting with matplotlib.

    Parameters
    ----------
    filename : str
        Filename of the alpha_div_collated file to be parsed. It is the result
        of QIIME's collate_alpha.py script.
    metric : str
        Provide the alpha diversity metric name, used to create the input file.
        Default is None, i.e. the metric name is guessed from the filename.

    Returns
    -------
    Pandas.DataFrame with the averaged (over all iterations) alpha diversities
    per rarefaction depth per sample.

    Raises
    ------
    IOError
        If the file cannot be read.
    """
    try:
        # read qiime's alpha div collated file. It is tab separated and nan
        # values come as 'n/a'
        x = pd.read_csv(filename, sep='\t', na_values=['n/a'])

        # make a two level index
        x.set_index(keys=['sequences per sample', 'iteration'], inplace=True)

        # remove the column that reports the single rarefaction files,
        # because it would otherwise become another sample
        del x['Unnamed: 0']

        # average over all X iterations
        x = x.groupby(['sequences per sample']).mean()

        # change pandas format of data for easy plotting
        x = x.stack().to_frame().reset_index()

        # guess metric name from filename
        if metric is None:
            metric = filename.split('/')[-1].split('.')[0]

        # give columns more appropriate names
        x = x.rename(columns={'sequences per sample': 'rarefaction depth',
                              'level_1': 'sample_name',
                              0: metric})

        # if there is only one (rarefaction) iteration, stacking results in a
        # slightly different DataFrame, which we are going to normalize here.
        if 'level_0' in x.columns:
            x['level_0'] = None
            x = x.rename(columns={'level_0': 'rarefaction depth'})

        return x
    except IOError:
        raise IOError('Cannot read file "%s"' % filename)


def _plot_rarefaction_curves(data):
    """Plot rarefaction curves along with loosing sample stats + read count
       histogram.

    Parameters
    ----------
    data : dict()
        The result of rarefaction_curves(), i.e. a dict with the three keys
        - metrics
        - remaining
        - readcounts

    Returns
    -------
    Matplotlib figure
    """
    fig, axes = plt.subplots(2+len(data['metrics']),
                             1,
                             figsize=(5, (2+len(data['metrics']))*5),
                             sharex=False)

    # read count histogram
    ax = axes[0]
    n, bins, patches = ax.hist(data['readcounts'],
                               50,
                               facecolor='black',
                               alpha=0.75)
    ax.set_title('Read count distribution across samples')
    ax.set_xlabel("read counts")
    ax.set_ylabel("# samples")
    ax.get_xaxis().set_major_formatter(
        FuncFormatter(lambda x, p: format(int(x), ',')))

    # loosing samples
    ax = axes[1]
    x = data['remaining']
    x['lost'] = data['readcounts'].shape[0] - x['remaining']
    x.index.name = 'readcounts'
    ax.plot(x.index, x['remaining'], label='remaining')
    ax.plot(x.index, x['lost'], label='lost')
    ax.set_xlabel("rarefaction depth")
    ax.set_ylabel("# samples")
    ax.set_title('How many of the %i samples do we loose?' %
                 data['readcounts'].shape[0])
    ax.get_xaxis().set_major_formatter(
        FuncFormatter(lambda x, p: format(int(x), ',')))
    lostHalf = abs(x['remaining'] - x['lost'])
    lostHalf = lostHalf[lostHalf == lostHalf.min()].index[0]
    ax.set_xlim(0, lostHalf * 1.1)
    # p = ax.set_xscale("log", nonposx='clip')

    for i, metric in enumerate(data['metrics'].keys()):
        for sample, g in data['metrics'][metric].groupby('sample_name'):
            axes[i+2].errorbar(g['rarefaction depth'], g[g.columns[-1]])
        axes[i+2].set_ylabel(g.columns[-1])
        axes[i+2].set_xlabel('rarefaction depth')
        axes[i+2].set_xlim(0, lostHalf * 1.1)
        axes[i+2].get_xaxis().set_major_formatter(
            FuncFormatter(lambda x, p: format(int(x), ',')))

    return fig


def rarefaction_curves(counts,
                       metrics=["PD_whole_tree", "shannon", "observed_otus"],
                       num_steps=20, reference_tree=None, max_depth=None,
                       num_iterations=10, **executor_args):
    """Produce rarefaction curves, i.e. reads/sample and alpha vs. depth plots.

    Parameters
    ----------
    counts : Pandas.DataFrame
        The raw read counts. Columns are samples, rows are features.
    metrics : [str]
        List of alpha diversity metrics to use.
        Default is ["PD_whole_tree", "shannon", "observed_otus"]
    num_steps : int
        Number of different rarefaction steps to test. The higher the slower.
        Default is 20.
    reference_tree : str
        Filepath to a newick tree file, which will be the phylogeny for unifrac
        alpha diversity distances. By default, qiime's GreenGenes tree is used.
    max_depth : int
        Maximal rarefaction depth. By default counts.sum().describe()['75%'] is
        used.
    num_iterations : int
        Default: 10.
        Number of iterations to rarefy the input table.
    executor_args:
        dry, use_grid, nocache, wait, walltime, ppn, pmem, timing, verbose

    Returns
    -------
    plt figure
    """
    def pre_execute(workdir, args):
        # store counts as a biom file
        pandas2biom(workdir+'/input.biom', args['counts'])

    def commands(workdir, ppn, args):
        max_rare_depth = args['counts'].sum().describe()['75%']
        if args['max_depth'] is not None:
            max_rare_depth = args['max_depth']
        commands = []

        # Alpha rarefaction command
        commands.append(('parallel_multiple_rarefactions.py '
                         '-T '
                         '-i %s '      # Input filepath, (the otu table)
                         '-m %i '      # Min seqs/sample
                         '-x %i '      # Max seqs/sample (inclusive)
                         '-s %i '      # Levels: min, min+step... for level
                                       # <= max
                         '-o %s '      # Write output rarefied otu tables here
                                       # makes dir if it doesn’t exist
                         '-n %i '      # number iterations per depth
                         '--jobs_to_start %i') % (  # Number of jobs to start
            workdir+'/input.biom',
            max(1000, args['counts'].sum().min()),
            max_rare_depth,
            (max_rare_depth - args['counts'].sum().min())/args['num_steps'],
            workdir+'/rare/rarefaction/',
            num_iterations,
            ppn))

        # Alpha diversity on rarefied OTU tables command
        commands.append(('parallel_alpha_diversity.py '
                         '-T '
                         '-i %s '         # Input path, must be directory
                         '-o %s '         # Output path, must be directory
                         '--metrics %s '  # Metrics to use, comma delimited
                         '-t %s '         # Path to newick tree file, required
                                          # for phylogenetic metrics
                         '--jobs_to_start %i') % (  # Number of jobs to start
            workdir+'/rare/rarefaction/',
            workdir+'/rare/alpha_div/',
            ",".join(args['metrics']),
            _get_ref_phylogeny(reference_tree),
            ppn))

        # Collate alpha command
        commands.append(('collate_alpha.py '
                         '-i %s '      # Input path (a directory)
                         '-o %s') % (  # Output path (a directory).
                                       # will be created if needed
            workdir+'/rare/alpha_div/',
            workdir+'/rare/alpha_div_collated/'))

        return commands

    def post_execute(workdir, args, pre_data):
        sums = args['counts'].sum()
        results = {'metrics': dict(),
                   'remaining': _getremaining(sums),
                   'readcounts': sums}
        for metric in args['metrics']:
            results['metrics'][metric] = _parse_alpha_div_collated(
                workdir+'/rare/alpha_div_collated/'+metric+'.txt')

        return results

    def post_cache(cache_results):
        cache_results['results'] = \
            _plot_rarefaction_curves(cache_results['results'])
        return cache_results

    return _executor('rare',
                     {'counts': counts,
                      'metrics': metrics,
                      'num_steps': num_steps,
                      'max_depth': max_depth,
                      'num_iterations': num_iterations},
                     pre_execute,
                     commands,
                     post_execute,
                     post_cache,
                     **executor_args)


def rarefy(counts, rarefaction_depth,
           ppn=1,
           **executor_args):
    """Rarefies a given OTU table to a given depth. This depth should be
       determined by looking at rarefaction curves.

    Paramaters
    ----------
    counts : Pandas.DataFrame
        OTU counts
    rarefaction_depth : int
        Rarefaction depth that must be applied to counts.
    executor_args:
        dry, use_grid, nocache, wait, walltime, ppn, pmem, timing, verbose

    Returns
    -------
    Pandas.DataFrame: Rarefied OTU table."""

    def pre_execute(workdir, args):
        # store counts as a biom file
        pandas2biom(workdir+'/input.biom', args['counts'])

    def commands(workdir, ppn, args):
        commands = []
        commands.append(('multiple_rarefactions.py '
                         '-i %s '                    # input biom file
                         '-m %i '                    # min rarefaction depth
                         '-x %i '                    # max rarefaction depth
                         '-s 1 '                     # depth steps
                         '-o %s '                    # output directory
                         '-n 1 '                  # number iterations per depth
                         ) % (   # number parallel jobs
            workdir+'/input.biom',
            args['rarefaction_depth'],
            args['rarefaction_depth'],
            workdir+'/rarefactions'))

        return commands

    def post_execute(workdir, args, pre_data):
        return biom2pandas(workdir+'/rarefactions/rarefaction_%i_0.biom' %
                           args['rarefaction_depth'])

    return _executor('rarefy',
                     {'counts': counts,
                      'rarefaction_depth': rarefaction_depth},
                     pre_execute,
                     commands,
                     post_execute,
                     ppn=ppn,
                     **executor_args)


def alpha_diversity(counts, rarefaction_depth,
                    metrics=["PD_whole_tree", "shannon", "observed_otus"],
                    num_iterations=10, reference_tree=None,
                    **executor_args):
    """Computes alpha diversity values for given BIOM table.

    Paramaters
    ----------
    counts : Pandas.DataFrame
        OTU counts
    rarefaction_depth : int
        Rarefaction depth that must be applied to counts.
    metrics : [str]
        Alpha diversity metrics to be computed.
    num_iterations : int
        Number of iterations to rarefy the input table.
    reference_tree : str
        Reference tree file name for phylogenetic metics like unifrac.
    executor_args:
        dry, use_grid, nocache, wait, walltime, ppn, pmem, timing, verbose

    Returns
    -------
    Pandas.DataFrame: alpha diversity values for each sample (rows) for every
    chosen metric (columns)."""

    def pre_execute(workdir, args):
        # store counts as a biom file
        pandas2biom(workdir+'/input.biom', args['counts'])

    def commands(workdir, ppn, args):
        commands = []

        if args['rarefaction_depth'] is not None:
            # rarefy input table
            commands.append(('parallel_multiple_rarefactions.py '
                             '-T '      # direct polling
                             '-i %s '   # input biom file
                             '-m %i '   # min rarefaction depth
                             '-x %i '   # max rarefaction depth
                             '-s 1 '    # depth steps
                             '-o %s '   # output directory
                             '-n %i '   # number iterations per depth
                             '--jobs_to_start %i') % (   # number parallel jobs
                workdir+'/input.biom',
                args['rarefaction_depth'],
                args['rarefaction_depth'],
                workdir+'/rarefactions',
                args['num_iterations'],
                ppn))
        else:
            os.mkdir(workdir+'/rarefactions')
            shutil.copyfile(workdir+'/input.biom',
                            workdir+'/rarefactions/rarefaction_0_0.biom')

        # compute alpha div values for rarefied tables
        # (or original input table, if rarefaction depth is None)
        commands.append(('parallel_alpha_diversity.py '
                         '-T '                      # direct polling
                         '-i %s '                   # dir to rarefied tables
                         '-o %s '                   # output directory
                         '--metrics %s '            # list of alpha div metrics
                         '-t %s '                   # tree reference file
                         '--jobs_to_start %i') % (  # number parallel jobs
            workdir+'/rarefactions/',
            workdir+'/alpha_div/',
            ",".join(args['metrics']),
            _get_ref_phylogeny(args['reference_tree']),
            ppn))

        # Collate alpha command
        commands.append(('collate_alpha.py '
                         '-i %s '      # Input path (a directory)
                         '-o %s') % (  # Output path (a directory).
                                       # will be created if needed
            workdir+'/alpha_div/',
            workdir+'/alpha_div_collated/'))

        return commands

    def post_execute(workdir, args, pre_data):
        results = []
        for metric in args['metrics']:
            a = _parse_alpha_div_collated(
                workdir+'/alpha_div_collated/'+metric+'.txt')
            a = a[['sample_name', metric]].set_index('sample_name')
            results.append(a)
        return pd.concat(results, axis=1)

    return _executor('adiv',
                     {'counts': counts,
                      'metrics': metrics,
                      'rarefaction_depth': rarefaction_depth,
                      'num_iterations': num_iterations,
                      'reference_tree': reference_tree},
                     pre_execute,
                     commands,
                     post_execute,
                     **executor_args)


def beta_diversity(counts,
                   metrics=["unweighted_unifrac",
                            "weighted_unifrac",
                            "bray_curtis"],
                   reference_tree=None, use_parallel=False,
                   **executor_args):
    """Computes beta diversity values for given BIOM table.

    Parameters
    ----------
    counts : Pandas.DataFrame
        OTU counts
    metrics : [str]
        Beta diversity metrics to be computed.
    reference_tree : str
        Reference tree file name for phylogenetic metics like unifrac.
    use_parallel : boolean
        Default: false. If true, use parallel version of beta div computation.
        I found that it often stalles with defunct processes.
    executor_args:
        dry, use_grid, nocache, wait, walltime, ppn, pmem, timing, verbose

    Returns
    -------
    Dict of Pandas.DataFrame, one per metric."""

    def pre_execute(workdir, args):
        # store counts as a biom file
        pandas2biom(workdir+'/input.biom', args['counts'])

    if use_parallel:
        def commands(workdir, ppn, args):
            commands = []
            commands.append(('parallel_beta_diversity.py '
                             '-i %s '              # input biom file
                             '-m %s '              # list of beta div metrics
                             '-t %s '              # tree reference file
                             '-o %s '
                             '-O %i ') % (
                workdir+'/input.biom',
                ",".join(args['metrics']),
                _get_ref_phylogeny(reference_tree),
                workdir+'/beta',
                ppn))
            return commands
    else:
        def commands(workdir, ppn, args):
            commands = []
            commands.append(('beta_diversity.py '
                             '-i %s '              # input biom file
                             '-m %s '              # list of beta div metrics
                             '-t %s '              # tree reference file
                             '-o %s ') % (
                workdir+'/input.biom',
                ",".join(args['metrics']),
                _get_ref_phylogeny(reference_tree),
                workdir+'/beta'))
            return commands

    def post_execute(workdir, args, pre_data):
        results = dict()
        for metric in args['metrics']:
            results[metric] = DistanceMatrix.read('%s/%s_input.txt' % (
                workdir+'/beta',
                metric))
        return results

    return _executor('bdiv',
                     {'counts': counts,
                      'metrics': metrics},
                     pre_execute,
                     commands,
                     post_execute,
                     **executor_args)


def sepp(counts, chunksize=10000, reference=None, stopdecomposition=None,
         ppn=20, pmem='8GB', walltime='12:00:00',
         **executor_args):
    """Tip insertion of deblur sequences into GreenGenes backbone tree.

    Parameters
    ----------
    counts : Pandas.DataFrame | Pandas.Series
        a) OTU counts in form of a Pandas.DataFrame.
        b) If providing a Pandas.Series, we expect the index to be a fasta
           headers and the colum the fasta sequences.
    reference : str
        Default: None.
        Valid values are ['pynast']. Use a different alignment file for SEPP.
    executor_args:
        dry, use_grid, nocache, wait, walltime, ppn, pmem, timing, verbose
    chunksize: int
        Default: 30000
        SEPP jobs seem to fail if too many sequences are submitted per job.
        Therefore, we can split your sequences in chunks of chunksize.

    Returns
    -------
    ???"""
    def pre_execute(workdir, args):
        chunks = range(0, seqs.shape[0], args['chunksize'])
        for chunk, i in enumerate(chunks):
            # write all deblur sequences into one file per chunk
            file_fragments = workdir + '/sequences%s.mfa' % (chunk + 1)
            f = open(file_fragments, 'w')
            chunk_seqs = seqs.iloc[i:i + args['chunksize']]
            for header, sequence in chunk_seqs.iteritems():
                f.write('>%s\n%s\n' % (header, sequence))
            f.close()

    def commands(workdir, ppn, args):
        commands = []
        commands.append('cd %s' % workdir)
        ref = ''
        if args['reference'] is not None:
            ref = ' -r %s' % args['reference']
        sdcomp = ''
        if 'stopdecomposition' in args:
            sdcomp = ' -M %f ' % args['stopdecomposition']
        commands.append('%srun-sepp.sh "%s" res${PBS_ARRAYID} -x %i %s %s' % (
            '/home/sjanssen/miniconda3/envs/seppGG_py3/src/sepp-package/',
            workdir+'/sequences${PBS_ARRAYID}.mfa',
            ppn,
            ref,
            sdcomp))
        return commands

    def post_execute(workdir, args, pre_data):
        files_placement = sorted(
            [workdir + '/' + file_placement
             for file_placement in next(os.walk(workdir))[2]
             if file_placement.endswith('_placement.json')])
        if len(files_placement) > 1:
            file_mergedplacements = workdir + '/merged_placements.json'
            if not os.path.exists(file_mergedplacements):
                sys.stderr.write("step 1) merging placement files: ")
                fout = open(file_mergedplacements, 'w')
                for i, file_placement in enumerate(files_placement):
                    sys.stderr.write('.')
                    fin = open(file_placement, 'r')
                    write = i == 0
                    for line in fin.readlines():
                        if '"placements": [{' in line:
                            write = True
                            if i != 0:
                                continue
                        if '}],' in line:
                            write = i+1 == len(files_placement)
                        if write is True:
                            fout.write(line)
                    fin.close()
                    if i+1 != len(files_placement):
                        fout.write('    },\n')
                        fout.write('    {\n')
                fout.close()
                sys.stderr.write(' done.\n')

            sys.stderr.write("step 2) placing fragments into tree: ...")
            # guppy ran for: and consumed 45 GB of memory for 2M, chunked 10k
            # sepp benchmark:
            # real	37m39.772s
            # user	31m3.906s
            # sys	3m49.602s
            file_merged_tree = file_mergedplacements[:-5] +\
                '.tog.relabelled.tre'
            cluster_run([
                'cd %s' % workdir,
                '/home/sjanssen/miniconda3/envs/seppGG_py3/src/sepp-package/'
                'sepp/.sepp/bundled-v4.3.0/guppy tog %s' %
                file_mergedplacements,
                'cat %s | python %s > %s' % (
                    file_mergedplacements.replace('.json', '.tog.tre'),
                    files_placement[0].replace('placement.json',
                                               'rename-json.py'),
                    file_merged_tree)],
                environment='seppGG_py3',
                jobname='guppy_rename',
                result=file_merged_tree,
                ppn=1, pmem='100GB', walltime='1:00:00', dry=False,
                wait=True)
            sys.stderr.write(' done.\n')
        else:
            file_merged_tree = files_placement[0].replace(
                '.json', '.tog.relabelled.tre')

        sys.stderr.write("step 3) reading skbio tree: ...")
        tree = TreeNode.read(file_merged_tree)
        sys.stderr.write(' done.\n')

        sys.stderr.write("step 4) use the phylogeny to det"
                         "ermine tips lineage: ")
        lineages = []
        features = []
        divisor = int(tree.count(tips=True) / min(10, tree.count(tips=True)))
        for i, tip in enumerate(tree.tips()):
            if i % divisor == 0:
                sys.stderr.write('.')
            if tip.name.isdigit():
                continue

            lineage = []
            for ancestor in tip.ancestors():
                try:
                    float(ancestor.name)
                except TypeError:
                    pass
                except ValueError:
                    lineage.append(ancestor.name)

            lineages.append("; ".join(reversed(lineage)))
            features.append(tip.name)
        sys.stderr.write(' done.\n')

        # storing tree as newick string is necessary since large trees would
        # result in too many recursions for the python heap :-/
        newick = StringIO()
        tree.write(newick)
        return {'taxonomy': pd.DataFrame(data=lineages,
                                         index=features,
                                         columns=['taxonomy']),
                'tree': newick.getvalue(),
                'reference': args['reference']}

    inp = sorted(counts.index)
    if type(counts) == pd.Series:
        # typically, the input is an OTU table with index holding sequences.
        # However, if provided a Pandas.Series, we expect index are sequence
        # headers and single column holds sequences.
        inp = counts.sort_index()

    def post_cache(cache_results):
        newicks = []
        for tree in cache_results['trees']:
            newicks.append(TreeNode.read(StringIO(tree)))
        cache_results['trees'] = newicks
        return cache_results

    seqs = inp
    if type(inp) != pd.Series:
        seqs = pd.Series(inp, index=inp).sort_index()
    args = {'seqs': seqs,
            'reference': reference,
            'chunksize': chunksize}
    if stopdecomposition is not None:
        args['stopdecomposition'] = stopdecomposition
    return _executor('sepp',
                     args,
                     pre_execute,
                     commands,
                     post_execute,
                     ppn=ppn, pmem=pmem, walltime=walltime,
                     array=len(range(0, seqs.shape[0], chunksize)),
                     **executor_args)


def sortmerna(sequences,
              reference='/projects/emp/03-otus/reference/97_otus.fasta',
              sortmerna_db='/projects/emp/03-otus/reference/97_otus.idx',
              ppn=5, pmem='20GB', walltime='2:00:00', **executor_args):
    """Assigns closed ref GreenGenes OTUids to sequences.

    Parameters
    ----------
    sequences : Pd.Series
        Set of sequences with header as index and nucleotide sequences as
        values.
    reference : filename
        Default: /projects/emp/03-otus/reference/97_otus.fasta
        Multiple fasta collection that serves as reference for sortmerna
        homology searches.
    sortmerna_db : filename
        Default: /projects/emp/03-otus/reference/97_otus.idx
        Can point to a precompiled reference DB. Make sure it matches your
        reference collection! Saves ~25min compute.
    executor_args:
        dry, use_grid, nocache, wait, walltime, ppn, pmem, timing, verbose

    Returns
    -------
    """
    def pre_execute(workdir, args):
        # store all unique sequences to a fasta file
        file_fragments = workdir + '/sequences.mfa'
        file_mapping = workdir + '/headermap.tsv'
        f = open(file_fragments, 'w')
        m = open(file_mapping, 'w')
        for i, (header, sequence) in enumerate(args['seqs'].iteritems()):
            f.write('>%s\n%s\n' % ('seq_%i' % i, sequence))
            m.write('seq_%i\t%s\n' % (i, header))
        f.close()
        m.close()

    def commands(workdir, ppn, args):
        commands = []
        precompileddb = ''
        if args['sortmerna_db'] is not None:
            precompileddb = ' --sortmerna_db %s ' % args['sortmerna_db']
        commands.append(('pick_otus.py '
                         '-m sortmerna '
                         '-i %s '
                         '-r %s '
                         '%s'
                         '-o %s '
                         '--sortmerna_e_value 1 '
                         '-s 0.97 '
                         '--threads %i ') % (
            workdir + '/sequences.mfa',
            args['reference'],
            precompileddb,
            workdir + '/sortmerna/',
            ppn))
        return commands

    def post_execute(workdir, args, pre_data):
        assignments = []

        # parse header mapping file
        hmap = pd.read_csv(workdir + '/headermap.tsv', sep='\t', header=None,
                           index_col=0)
        # parse sucessful sequence to OTU assignments
        f = open(workdir+'/sortmerna/sequences_otus.txt', 'r')
        for line in f.readlines():
            parts = line.rstrip().split('\t')
            for header in parts[1:]:
                assignments.append({'otuid': parts[0],
                                    'header': hmap.loc[header].iloc[0]})
        f.close()

        # parse failed sequences
        f = open(workdir+'/sortmerna/sequences_failures.txt', 'r')
        for line in f.readlines():
            assignments.append({'header': line.rstrip()})
        f.close()

        return pd.DataFrame(assignments).set_index('header')

    if not os.path.exists(reference):
        raise ValueError('Reference multiple fasta file "%s" does not exist!' %
                         reference)

    if sortmerna_db is not None:
        if not os.path.exists(sortmerna_db+'.stasts'):
            sys.stderr.write('Could not find SortMeRNA precompiled DB. '
                             'I continue by creating a new DB.')
    # core dump with 8GB with 10 nodes, 4h
    # trying 20GB with 10 nodes ..., 4h (long wait for scheduler)
    # trying 20GB with 5 nodes, 2h ...
    return _executor('sortmerna',
                     {'seqs': sequences.drop_duplicates().sort_index(),
                      'reference': reference,
                      'sortmerna_db': sortmerna_db},
                     pre_execute,
                     commands,
                     post_execute,
                     ppn=ppn,
                     pmem=pmem,
                     walltime=walltime,
                     **executor_args)


def _parse_timing(workdir, jobname):
    """If existant, parses timing information.

    Parameters
    ----------
    workdir : str
        Path to tmp workdir of _executor containing cr_ana_<jobname>.t* file
    jobname : str
        Name of ran job.

    Parameters
    ----------
    None if file could not be found. Otherwise: [str]
    """
    files_timing = [workdir + '/' + d
                    for d in next(os.walk(workdir))[2]
                    if 'cr_ana_%s.t' % jobname in d]
    for file_timing in files_timing:
        with open(file_timing, 'r') as content_file:
            return content_file.readlines()
        # stop after reading first found file, since there should only be one
        break
    return None


def _executor(jobname, cache_arguments, pre_execute, commands, post_execute,
              post_cache=None,
              dry=True, use_grid=True, ppn=10, nocache=False,
              pmem='8GB', environment=QIIME_ENV, walltime='4:00:00',
              wait=True, timing=True, verbose=True, array=1):
    """

    Parameters
    ----------
    jobname : str
    cache_arguments : []
    pre_execute : function
    commands : []
    post_execute : function
    post_cache : function
        A function that is called, after results have been loaded from cache /
        were generated. E.g. drawing rarefaction curves.
    environment : str

    ==template arguments that should be copied to calling analysis function==
    dry : bool
        Default: True.
        If True: only prepare working directory and create necessary input
        files and print the command that would be executed in a non dry run.
        For debugging. Workdir is not deleted.
        "pre_execute" is called, but not "post_execute".
    use_grid : bool
        Default: True.
        If True, use qsub to schedule as a grid job, otherwise run locally.
    nocache : bool
        Default: False.
        Normally, successful results are cached in .anacache directory to be
        retrieved when called a second time. You can deactivate this feature
        (useful for testing) by setting "nocache" to True.
    wait : bool
        Default: True.
        Wait for results.
    walltime : str
        Default: "12:00:00".
        hh:mm:ss formated wall runtime on cluster.
    ppn : int
        Default: 10.
        Number of CPU cores to be used.
    pmem : str
        Default: '8GB'.
        Resource request for cluster jobs. Multiply by ppn!
    timing : bool
        Default: True
        Use '/usr/bin/time' to log run time of commands.
    verbose : bool
        Default: True
        If True, report progress on sys.stderr.
    array : int
        Default: 1 = deactivated.
        Only for Torque submits: make the job an array job.
        You need to take care of correct use of ${PBS_JOBID} !

    Returns
    -------
    """
    DIR_CACHE = '.anacache'
    FILE_STATUS = 'finished.info'
    results = {'results': None,
               'workdir': None,
               'qid': None,
               'file_cache': None,
               'timing': None,
               'cache_version': 20170817,
               'created_on': None,
               'jobname': jobname}
    DIR_TMP_TEMPLATE = '/home/sjanssen/TMP/'

    # create an ID function if no post_cache function is supplied
    def _id(x):
        return x
    if post_cache is None:
        post_cache = _id

    # phase 1: compute signature for cache file
    _input = collections.OrderedDict(sorted(cache_arguments.items()))
    results['file_cache'] = "%s/%s.%s" % (DIR_CACHE, hashlib.md5(
        str(_input).encode()).hexdigest(), jobname)

    # phase 2: if cache contains matching file, load from cache and return
    if os.path.exists(results['file_cache']) and (nocache is not True):
        if verbose:
            sys.stderr.write("Using existing results from '%s'. \n" %
                             results['file_cache'])
        f = open(results['file_cache'], 'rb')
        results = pickle.load(f)
        f.close()
        return post_cache(results)

    # phase 3: search in TMP dir if non-collected results are
    # ready or are waited for
    dir_tmp = tempfile.gettempdir()
    if use_grid:
        dir_tmp = DIR_TMP_TEMPLATE

    # collect all tmp workdirs that contain the right cache signature
    pot_workdirs = [x[0]  # report directory name
                    for x in os.walk(dir_tmp)
                    # shares same cache signature:
                    if results['file_cache'].split('/')[-1] in x[2]]
    finished_workdirs = []
    for wd in pot_workdirs:
        all_finished = True
        for i in range(array):
            if not os.path.exists(wd+'/finished.info%i' % (i+1)):
                all_finished = False
                break
        if all_finished:
            finished_workdirs.append(wd)
    if len(pot_workdirs) > 0 and len(finished_workdirs) <= 0:
        if verbose:
            sys.stderr.write(
                ('Found %i temporary working directories, but non of '
                 'them have finished. If no job is currently running,'
                 ' you might want to delete these directories and res'
                 'tart:\n  %s\n') % (len(pot_workdirs),
                                     "\n  ".join(pot_workdirs)))
        return results
    if len(finished_workdirs) > 0:
        # arbitrarily pick first found workdir
        results['workdir'] = finished_workdirs[0]
        if verbose:
            sys.stderr.write('found matching working dir "%s"\n' %
                             results['workdir'])
        pre_data = pre_execute(results['workdir'], cache_arguments)
    else:
        # create a temporary working directory
        prefix = 'ana_%s_' % jobname
        results['workdir'] = tempfile.mkdtemp(prefix=prefix, dir=dir_tmp)
        if verbose:
            sys.stderr.write("Working directory is '%s'. " %
                             results['workdir'])
        # leave an empty file in workdir with cache file name to later
        # parse results from tmp dir
        f = open("%s/%s" % (results['workdir'],
                            results['file_cache'].split('/')[-1]), 'w')
        f.close()

        pre_data = pre_execute(results['workdir'], cache_arguments)

        lst_commands = commands(results['workdir'], ppn, cache_arguments)
        # device creation of a file _after_ execution of the job in workdir
        lst_commands.append('touch %s/%s${PBS_ARRAYID}' %
                            (results['workdir'], FILE_STATUS))
        if not use_grid:
            if dry:
                if verbose:
                    sys.stderr.write("\n\n".join(lst_commands))
                return results
            if timing:
                _add_timing_cmds(lst_commands,
                                 results['workdir'] +
                                 '/timing${PBS_ARRAYID}.txt')
            with subprocess.Popen("source activate %s && %s" %
                                  (environment, " && ".join(lst_commands)),
                                  shell=True,
                                  stdout=subprocess.PIPE,
                                  executable="bash") as call_x:
                if (call_x.wait() != 0):
                    rescmd = subprocess.check_output(
                        'ls -la %s/*' % results['workdir'],
                        shell=True).decode().split('\n')
                    for line in rescmd:
                        print(line)
                    raise ValueError(("something went wrong with conda "
                                      "activation"))
        else:
            results['qid'] = cluster_run(
                lst_commands, 'ana_%s' % jobname, results['workdir']+'mock',
                environment, ppn=ppn, wait=wait, dry=dry,
                pmem=pmem, walltime=walltime,
                file_qid=results['workdir']+'/cluster_job_id.txt',
                timing=timing,
                file_timing=results['workdir']+('/timing${PBS_ARRAYID}.txt'),
                array=array)
            if dry:
                return results
            if wait is False:
                return results

    results['results'] = post_execute(results['workdir'],
                                      cache_arguments,
                                      pre_data)
    results['created_on'] = datetime.datetime.fromtimestamp(
        time.time()).strftime('%Y-%m-%d %H:%M:%S')

    results['timing'] = []
    for timingfile in next(os.walk(results['workdir']))[2]:
        if timingfile.startswith('timing'):
            with open(results['workdir']+'/'+timingfile, 'r') as content_file:
                results['timing'] += content_file.readlines()

    if results['results'] is not None:
        shutil.rmtree(results['workdir'])
        if verbose:
            sys.stderr.write(" Was removed.\n")

    os.makedirs(os.path.dirname(results['file_cache']), exist_ok=True)
    f = open(results['file_cache'], 'wb')
    pickle.dump(results, f)
    f.close()

    return post_cache(results)
