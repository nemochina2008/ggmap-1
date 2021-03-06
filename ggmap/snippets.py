import pandas as pd
import biom
from biom.util import biom_open
from mpl_toolkits.basemap import Basemap
from itertools import repeat, chain
import numpy as np
import matplotlib.patches as mpatches
from matplotlib.font_manager import FontProperties
import os
import seaborn as sns
import matplotlib.pyplot as plt
import subprocess
import sys
import time
from itertools import combinations
from skbio.stats.distance import permanova
from scipy.stats import mannwhitneyu
import networkx as nx
import warnings
import matplotlib.cbook
import random
from tempfile import mkstemp
import pickle


RANKS = ['Kingdom', 'Phylum', 'Class', 'Order', 'Family', 'Genus', 'Species']
EXEC_TIME = '/usr/bin/time'


def biom2pandas(file_biom, withTaxonomy=False, astype=int):
    """ Converts a biom file into a Pandas.DataFrame

    Parameters
    ----------
    file_biom : str
        The path to the biom file.
    withTaxonomy : bool
        If TRUE, returns a second Pandas.Series with lineage information for
        each feature, e.g. OTU or deblur-sequence. Default: FALSE
    astype : type
        datatype into each value of the biom table is casted. Default: int.
        Use e.g. float if biom table contains relative abundances instead of
        raw reads.

    Returns
    -------
    A Pandas.DataFrame holding holding numerical values from the biom file.
    If withTaxonomy is TRUE then a second Pandas.DataFrame is returned, holding
    lineage information about each feature.

    Raises
    ------
    IOError
        If file_biom cannot be read.
    ValueError
        If withTaxonomy=TRUE but biom file does not hold taxonomy information.
    """
    try:
        table = biom.load_table(file_biom)
        counts = pd.DataFrame(table.matrix_data.T.todense().astype(astype),
                              index=table.ids(axis='sample'),
                              columns=table.ids(axis='observation')).T
        if withTaxonomy:
            try:
                md = table.metadata_to_dataframe('observation')
                levels = [col
                          for col in md.columns
                          if col.startswith('taxonomy_')]
                if levels == []:
                    raise ValueError(('No taxonomy information found in '
                                      'biom file.'))
                else:
                    taxonomy = md.apply(lambda row:
                                        ";".join([row[l] for l in levels]),
                                        axis=1)
                    return counts, taxonomy
            except KeyError:
                raise ValueError(('Biom file does not have any '
                                  'observation metadata!'))
        else:
            return counts
    except IOError:
        raise IOError('Cannot read file "%s"' % file_biom)


def pandas2biom(file_biom, table, taxonomy=None, err=sys.stderr):
    """ Writes a Pandas.DataFrame into a biom file.

    Parameters
    ----------
    file_biom: str
        The filename of the BIOM file to be created.
    table: a Pandas.DataFrame
        The table that should be written as BIOM.
    taxonomy : pandas.Series
        Index is taxons corresponding to table, values are lineage strings like
        'k__Bacteria; p__Actinobacteria'
    err : StringIO
        Stream onto which errors / warnings should be printed.
        Default is sys.stderr
    Raises
    ------
    IOError
        If file_biom cannot be written.

    TODO
    ----
        1) also store taxonomy information
    """
    try:
        bt = biom.Table(table.values,
                        observation_ids=table.index,
                        sample_ids=table.columns)

        # add taxonomy metadata if provided, i.e. is not None
        if taxonomy is not None:
            if not isinstance(taxonomy, pd.core.series.Series):
                raise AttributeError('taxonomy must be a pandas.Series!')
            idx_missing_intable = set(table.index) - set(taxonomy.index)
            if len(idx_missing_intable) > 0:
                err.write(('Warning: following %i taxa are not in the '
                           'provided taxonomy:\n%s\n') % (
                          len(idx_missing_intable),
                          ", ".join(idx_missing_intable)))
            idx_missing_intaxonomy = set(taxonomy.index) - set(table.index)
            if len(idx_missing_intaxonomy) > 0:
                err.write(('Warning: following %i taxa are not in the '
                           'provided count table, but in taxonomy:\n%s\n') % (
                          len(idx_missing_intaxonomy),
                          ", ".join(idx_missing_intaxonomy)))

            t = dict()
            for taxon, linstr in taxonomy.iteritems():
                # fill missing rank annotations with rank__
                orig_lineage = {annot[0].lower(): annot
                                for annot
                                in (map(str.strip, linstr.split(';')))}
                lineage = []
                for rank in RANKS:
                    rank_char = rank[0].lower()
                    if rank_char in orig_lineage:
                        lineage.append(orig_lineage[rank_char])
                    else:
                        lineage.append(rank_char+'__')
                t[taxon] = {'taxonomy': ";".join(lineage)}
            bt.add_metadata(t, axis='observation')

        with biom_open(file_biom, 'w') as f:
            bt.to_hdf5(f, "example")
    except IOError:
        raise IOError('Cannot write to file "%s"' % file_biom)


def parse_splitlibrarieslog(filename):
    """ Parse the log of a QIIME split_libraries_xxx.py run.

    Especially deal with multiple input files, i.e. several sections in log.

    Parameters
    ----------
    filename : str
        The filename of the log to parse.

    Returns
    -------
    A Pandas.DataFrame containing two column with 'counts' and sample name for
    each sample in the log file.
    (We might see duplicate sample names from multiple input files, thus we
     cannot make the sample name the index.)

    Raises
    ------
    IOError
        If filename cannot be read.
    """
    try:
        counts = []
        f = open(filename, 'r')
        endOfFile = False
        while not endOfFile:
            # find begin of count table
            while True:
                line = f.readline()
                if 'Median sequence length:' in line:
                    break
            # collect counts
            while True:
                line = f.readline()
                if line == '\n':
                    break
                samplename, count = line.split()
                counts.append({'sample': samplename, 'counts': count})
            # check if file contains more blocks
            while True:
                line = f.readline()
                if 'Input file paths' in line:
                    break
                if line == '':
                    endOfFile = True
                    break
        return pd.DataFrame(sorted(counts,
                                   key=lambda x: int(x['counts']),
                                   reverse=True), dtype=int)
    except IOError:
        raise IOError('Cannot read file "%s"' % filename)


def drawMap(points, basemap=None, ax=None, no_legend=False):
    """ Plots coordinates of metadata to a worldmap.

    Parameters
    ----------
    points : a set if dicts, with mandatory key
        'coords', which itself needs to be a Pandas DataFrame with columns
            'latitude' and
            'longitude'.
        Optional keys are:
        'color' = color of points drawn onto the map (defaults to 'red'),
        'size' = diameter of drawn points (defaults to 50),
        'alpha' = transparency of points (defaults to 0.5)
        'label' = a name for the group of points, useful if more than one dict
                  is supplied
    basemap : Default is None, i.e. the whole world is plotted. By providing a
        basemap object, you can restrict the plotted map to a specific
        rectangle, e.g. to Alaska region with:
            Basemap(llcrnrlat=43.,
                    llcrnrlon=168.,
                    urcrnrlat=63.,
                    urcrnrlon=-110,
                    resolution='i',
                    projection='cass',
                    lat_0 = 90.,
                    lon_0 = -155.
    ax : plt.axis
        Default is none, i.e. create a new figure. Otherwise, provide axis onto
        which shall be drawn.
    no_legend : bool
        Default is False. Set to True to suppress drawing a legend.

    Returns
    -------
    plt.axis onto which was plotted.

    Raises
    ------
    ValueError if provided list of dicts do not contain keys 'coords' or
    coords DataFrame is lacking columns 'latitude' or 'longitude'.
    """
    if ax is None:
        fig, ax = plt.subplots(1, 1)

    map = None
    if basemap is None:
        map = Basemap(projection='robin', lon_0=180, resolution='c', ax=ax)
    else:
        map = basemap

    # Fill the globe with a blue color
    map.drawmapboundary(fill_color='lightblue', color='white')
    # Fill the continents with the land color
    map.fillcontinents(color='lightgreen', lake_color='lightblue', zorder=1)
    map.drawcoastlines(color='gray', zorder=1)

    l_patches = []
    for z, set_of_points in enumerate(points):
        if 'coords' not in set_of_points:
            raise ValueError('You need to provide key'
                             ' "coords" for every dict!')
        if 'latitude' not in set_of_points['coords'].columns:
            raise ValueError('Given "coords" need to have column "latitude"')
        if 'longitude' not in set_of_points['coords'].columns:
            raise ValueError('Given "coords" need to have column "longitude"')
        coords = set_of_points['coords'][['latitude', 'longitude']].dropna()
        x, y = map(coords.longitude.values, coords.latitude.values)
        size = 50
        if 'size' in set_of_points:
            size = set_of_points['size']
        alpha = 0.5
        if 'alpha' in set_of_points:
            alpha = set_of_points['alpha']
        color = 'red'
        if 'color' in set_of_points:
            color = set_of_points['color']
        map.scatter(x, y, marker='o', color=color, s=size,
                    zorder=2+z, alpha=alpha)
        if 'label' in set_of_points:
            l_patches.append(mpatches.Patch(color=color,
                                            label=set_of_points['label']))

    if (len(l_patches) > 0) & (no_legend is not True):
        ax.legend(handles=l_patches, loc='upper left',
                  bbox_to_anchor=(1.01, 1))

    return ax


def _repMiddleValues(values):
    """ Takes a list of values and repeats each value once.

    Example: [1,2,3] -> [1,1,2,2,3,3]

    Parameters
    ----------
    values : [a]

    Returns
    -------
    [a] where each element has been duplicated.
    """

    return list(chain.from_iterable(repeat(v, 2) for v in values))


def _shiftLeft(values):
    """ All list elements are shifted left. Leftmost element is lost, new right
        elements is last element +1.

    Parameters
    ----------
    values : [int]

    Returns
    -------
    [int]: A list where first element is lost, elements shift one position to
    the left and last element is last input element +1.
    """
    return values[1:]+[values[-1]+1]


def _get_sample_numbers(num_samples, fields, names):
    """Given a table about the number of available samples, this function
       returns the number of samples for the given group.

    Parameters
    ----------
    num_samples : pd.DataFrame
        Number of samples per group for all set groups.
    field : [str]
        grouping names, must be included in metadata and therefore implicitly
        in num_samples
    names : [str]
        Group name.

    Returns
    -------
    int : number of samples for the given group.

    """
    x = num_samples
    for field, name in zip(fields, names):
        if field is not None:
            x = x[x[field] == name]
    return x[0].sum()


def collapseCounts(file_otutable, rank,
                   file_taxonomy=None,
                   verbose=True, out=sys.stdout, astype=int):
    """Collapses features of an OTU table according to their taxonomic
       assignment and a given rank.

    Parameters
    ----------
    file_otutable : file
        Path to a biom OTU table
    rank : str
        Set taxonomic level to collapse abundances. Use 'raw' to de-activate
        collapsing.
    file_taxonomy : file
        Taxonomy information is read from the biom file. Except you provide an
        alternative taxonomy in terms of a two column file. First column must
        contain feature ID (OTUid or sequence), second colum is the ; separated
        lineage string.
        Default is None, i.e. using taxonomy from biom file.
    verbose : bool
        Default is true. Report messages if true.
    out : StringIO
        Buffer onto which messages should be written. Default is sys.stdout.
    astype : type
        datatype into each value of the biom table is casted. Default: int.
        Use e.g. float if biom table contains relative abundances instead of
        raw reads.

    Returns
    -------
    Pandas.DataFrame: counts of collapsed taxa.
    """
    # check that rank is a valid taxonomic rank
    if rank not in RANKS + ['raw']:
        raise ValueError('"%s" is not a valid taxonomic rank. Choose from %s' %
                         (rank, ", ".join(RANKS)))

    # check that biom table can be read
    if not os.path.exists(file_otutable):
        raise IOError('OTU table file not found')

    counts, taxonomy = None, None
    if file_taxonomy is None:
        counts, taxonomy = biom2pandas(file_otutable, withTaxonomy=True,
                                       astype=astype)
        taxonomy.name = 'taxonomy'
        rank_counts = pd.merge(counts, taxonomy.to_frame(), how='left',
                               left_index=True, right_index=True)
    else:
        # check that taxonomy file exists
        if (not os.path.exists(file_taxonomy)) and (rank != 'raw'):
            raise IOError('Taxonomy file not found!')

        counts = biom2pandas(file_otutable, withTaxonomy=False, astype=astype)
        if rank != 'raw':
            taxonomy = pd.read_csv(file_taxonomy, sep="\t", header=None,
                                   names=['otuID', 'taxonomy'],
                                   usecols=[0, 1])  # only parse 2 first cols
            taxonomy['otuID'] = taxonomy['otuID'].astype(str)
            taxonomy.set_index('otuID', inplace=True)
            # add taxonomic lineage information to the counts as
            # column "taxonomy"
            rank_counts = pd.merge(counts, taxonomy, how='left',
                                   left_index=True, right_index=True)

    if rank != 'raw':
        # split lineage string into individual taxa names on ';' and remove
        # surrounding whitespaces. If rank does not exist return r+'__' instead
        def _splitranks(x, rank):
            try:
                return [t.strip() for t in x.split(";")][RANKS.index(rank)]
            except AttributeError:
                # e.g. if lineage string is missing
                RANKS[RANKS.index(rank)].lower()[0] + "__"
            except IndexError:
                return RANKS[RANKS.index(rank)].lower()[0] + "__"
        # add columns for each tax rank, such that we can groupby later on
        rank_counts[rank] = rank_counts['taxonomy'].apply(lambda x:
                                                          _splitranks(x, rank))
        # sum counts according to the selected rank
        rank_counts = rank_counts.reset_index().groupby(rank).sum()
        # get rid of the old index, i.e. OTU ids, since we have grouped by some
        # rank

        if verbose:
            out.write('%i taxa left after collapsing to %s.\n' %
                      (rank_counts.shape[0], rank))
    else:
        rank_counts = counts

    return rank_counts


def plotTaxonomy(file_otutable,
                 metadata,
                 group_l0=None,
                 group_l1=None,
                 group_l2=None,
                 rank='Phylum',
                 file_taxonomy=('/projects/emp/03-otus/reference/'
                                '97_otu_taxonomy.txt'),
                 verbose=True,
                 reorder_samples=False,
                 print_sample_labels=False,
                 minreadnr=50,
                 plottaxa=None,
                 fct_aggregate=None,
                 no_top_labels=False,
                 grayscale=False,
                 out=sys.stdout,
                 taxonomy_from_biom=False,
                 no_sample_numbers=False,
                 colors=None,
                 min_abundance_grayscale=0,
                 ax=None):
    """Plot taxonomy.

    Parameters
    ----------
    file_otutable : file
        Path to a biom OTU table
    metadata : pandas.DataFrame
        metadata
    file_taxonomy : file
        Path to a GreenGenes taxonomy file.
    reorder_samples : Bool
        True = sort samples in each group according to abundance of most
        abundant taxon
    print_sample_labels : Bool
        True = print sample names on x-axis. Use only for small numbers of
        samples!
    minreadnr : int
        min number of reads a taxon need to have to be plotted
    plottaxa : [str]
        Only plot abundances for taxa IDs provided. If None, all taxa are
        plotted. Default: None
    rank : str
        Set taxonomic level to collapse abundances. Use 'raw' to de-activate
        collapsing.
    fct_aggregate : function
        A numpy function to aggregate over several samples.
    no_top_labels : Bool
        If True, print no labels on top of the bars. Default is False.
    grayscale : Bool
        If True, plot low abundant taxa with gray scale values.
    taxonomy_from_biom : Bool
        Default is False. If true, read taxonomy information from input biom
        file.
    no_sample_numbers : Bool
        Default is False. If true, no n= sample numbers will be reported.
    colors : dict(taxon: (r, g, b))
        Provide a predefined color dictionary to use same colors for several
        plots. Default is an empty dictionary.
        Format: key = taxon name,
        Value: a triple of RGB float values.
    min_abundance_grayscale : float
        Stop drawing gray rectangles for low abundant taxa if their relative
        abundance is below this threshold. Saves time and space.
    ax : plt.axis
        Plot on this axis instead of creating a new figure. Only works if
        number of group levels is <= 2.

    Returns
    -------
    fig, rank_counts, graphinfo, vals, color-dict
    """

    NAME_LOW_ABUNDANCE = 'low abundance'
    GRAYS = ['#888888', '#EEEEEE', '#999999', '#DDDDDD', '#AAAAAA',
             '#CCCCCC', '#BBBBBB']
    random.seed(42)

    # Parameter checks: check that grouping fields are in metadata table
    for i, field in enumerate([group_l0, group_l1, group_l2]):
        if field is not None:
            if field not in metadata.columns:
                raise ValueError(('Column "%s" for grouping level %i is not '
                                  'in metadata table!') % (field, i))

    ft = file_taxonomy
    if taxonomy_from_biom:
        ft = None
    rawcounts = collapseCounts(file_otutable, rank, file_taxonomy=ft,
                               verbose=verbose, out=out)

    # restrict to those samples for which we have metadata AND counts
    meta = metadata.loc[[idx
                         for idx in metadata.index
                         if idx in rawcounts.columns], :]
    rank_counts = rawcounts.loc[:, meta.index]
    if verbose:
        out.write('%i samples left with metadata and counts.\n' %
                  meta.shape[0])

    lowAbundandTaxa = rank_counts[(rank_counts.sum(axis=1) < minreadnr)].index
    highAbundantTaxa = rank_counts[(rank_counts.sum(axis=1) >=
                                    minreadnr)].index

    # normalize to 1 in each sample
    rank_counts /= rank_counts.sum(axis=0)

    # filter low abundant taxa
    if (grayscale is False) & (len(lowAbundandTaxa) > 0):
        lowReadTaxa = rank_counts.loc[lowAbundandTaxa, :].sum(axis=0)
        lowReadTaxa.name = NAME_LOW_ABUNDANCE
        rank_counts = rank_counts.loc[highAbundantTaxa, :]
        rank_counts = rank_counts.append(lowReadTaxa)
        if verbose:
            out.write('%i taxa left after filtering low abundant.\n' %
                      (rank_counts.shape[0]-1))

    # restrict to those taxa that are asked for in plottaxa
    if plottaxa is not None:
        rank_counts = rank_counts.loc[plottaxa, :]
        if verbose:
            out.write('%i taxa left after restricting to provided list.\n' %
                      (rank_counts.shape[0]))

    # all for plotting
    # sort taxa according to sum of abundance
    taxaidx = list(rank_counts.mean(axis=1).sort_values(ascending=False).index)
    if (grayscale is False) & (len(lowAbundandTaxa) > 0):
        taxaidx = [taxon
                   for taxon in taxaidx
                   if taxon != NAME_LOW_ABUNDANCE] + [NAME_LOW_ABUNDANCE]
    elif grayscale is True:
        taxaidx = [taxon for taxon in taxaidx if taxon in highAbundantTaxa] +\
                  [taxon for taxon in taxaidx if taxon not in highAbundantTaxa]
    rank_counts = rank_counts.loc[taxaidx, :]

    levels = [f for f in [group_l2, group_l1, group_l0] if f is not None]

    # keeping track of correct sample numbers
    num_samples = meta.shape[0]
    if levels != []:
        num_samples = meta.groupby(levels).size().reset_index()

    # aggregate over samples
    if fct_aggregate is not None:
        if len(levels) < 1:
            raise ValueError("Cannot aggregate samples, "
                             "if no grouping is given!")
        # return rank_counts, meta, levels, None
        grs = dict()
        newmeta = dict()
        for n, g in meta.groupby(list(reversed(levels))):
            for sampleid in g.index:
                if isinstance(n, tuple):
                    grs[sampleid] = "###".join(list(map(str, n)))
                else:
                    grs[sampleid] = str(n)
            if isinstance(n, tuple):
                x = dict(zip(reversed(levels), n))
            else:
                x = {levels[0]: n}
            x['num'] = g.shape[0]
            if isinstance(n, tuple):
                newmeta["###".join(list(map(str, n)))] = x
            else:
                newmeta[str(n)] = x
        rank_counts = rank_counts.T.groupby(by=grs).agg(fct_aggregate).T
        meta = pd.DataFrame(newmeta).T
        group_l0, group_l1, group_l2 = None, group_l0, group_l1

    # prepare abundances for plot
    vals = rank_counts.cumsum()

    # collect information about how to plot data
    graphinfo = pd.DataFrame(data=None, index=vals.columns)
    if group_l0 is None:
        meta['help_plottaxonomy_level_0'] = 'all'
        grps0 = meta.groupby('help_plottaxonomy_level_0')
    else:
        grps0 = meta.groupby(group_l0)
    for i0, (n0, g0) in enumerate(grps0):
        graphinfo.loc[g0.index, 'group_l0'] = n0

        grps1 = [('all', g0)]
        if group_l1 is not None:
            grps1 = g0.groupby(group_l1)
        offset = 0
        for i1, (n1, g1) in enumerate(grps1):
            sample_idxs = vals.iloc[0, :].loc[g1.index]
            if reorder_samples:
                sample_idxs = sample_idxs.sort_values(ascending=False)
            sample_idxs = sample_idxs.index
            if group_l2 is not None:
                help_sample_idxs = []
                for n2, g2 in g0.loc[g1.index, :].groupby(group_l2):
                    reorderd = [idx for idx in sample_idxs if idx in g2.index]
                    help_sample_idxs.extend(reorderd)
                    graphinfo.loc[reorderd, 'group_l2'] = n2
                sample_idxs = help_sample_idxs
            graphinfo.loc[sample_idxs, 'group_l1'] = n1
            graphinfo.loc[sample_idxs, 'xpos'] = range(offset,
                                                       offset+len(sample_idxs))
            offset += len(sample_idxs)
            if i1 < len(grps1):
                offset += max(1, int(g0.shape[0]*0.05))

    # define colors for taxons
    availColors = \
        sns.color_palette('Paired', 12) +\
        sns.color_palette('Dark2', 12) +\
        sns.color_palette('Pastel1', 12)
    if colors is None:
        colors = dict()
    colors[NAME_LOW_ABUNDANCE] = 'white'
    for i in range(0, vals.shape[0]):
        taxon = vals.index[i]
        if taxon not in colors:
            colors[taxon] = availColors[len(colors) % len(availColors)]

    # plot the actual thing
    if (ax is not None):
        if len(grps0) > 1:
            raise Exception('You cannot provide an ax if number of '
                            'grouping levels is > 2!')
        else:
            axarr = ax
            fig = ax
    else:
        fig, axarr = plt.subplots(len(grps0), 1)
    num_saved_boxes = 0
    for ypos, (n0, g0) in enumerate(graphinfo.groupby('group_l0')):
        if group_l0 is None:
            ax = axarr
        else:
            ax = axarr[ypos]
        for i in range(0, vals.shape[0]):
            taxon = vals.index[i]
            color = colors[taxon]
            if taxon in lowAbundandTaxa:
                color = random.choice(GRAYS)
            y_prev = None
            for j, (name, g1_idx) in enumerate(graphinfo.loc[g0.index, :]
                                               .groupby('group_l1')):
                if i == 0:
                    y_prev = [0] * g1_idx.shape[0]
                else:
                    y_prev = vals.loc[:, g1_idx.sort_values(by='xpos').index]\
                        .iloc[i-1, :]
                    if grayscale & (y_prev.min() > 1-min_abundance_grayscale):
                        num_saved_boxes += 1
                        continue
                y_curr = vals.loc[:, g1_idx.sort_values(by='xpos').index]\
                    .iloc[i, :]
                xpos = g1_idx.sort_values(by='xpos')['xpos']

                ax.fill_between(_shiftLeft(_repMiddleValues(xpos)),
                                _repMiddleValues(y_prev),
                                _repMiddleValues(y_curr),
                                color=color)

            if grayscale & \
               (vals.iloc[i, :].min() >= 1-min_abundance_grayscale):
                num_saved_boxes += len(graphinfo.loc[g0.index,
                                                     'group_l1'].unique())
                break

        # decorate graph with axes labels ...
        if print_sample_labels:
            ax.set_xticks(graphinfo.loc[g0.index, :]
                          .sort_values(by='xpos')['xpos']+.5)
            # determine sample lables, which might be aggregated
            data = graphinfo[['xpos']]
            if fct_aggregate is not None:
                data = graphinfo[['xpos']].merge(meta[['num']],
                                                 left_index=True,
                                                 right_index=True)
            labels = []
            for idx, row in data.sort_values(by='xpos').iterrows():
                if '###' in idx:
                    label = "%s" % idx.split('###')[-1]
                else:
                    label = idx
                if 'num' in row.index:
                    label += " (n=%i)" % row['num']
                labels.append(label)
            ax.set_xticklabels(labels, rotation='vertical')
            ax.xaxis.set_ticks_position("bottom")
        else:
            ax.set_xticks([])

        # crop graph to actually plotted bars
        ax.set_xlim(0, graphinfo.loc[g0.index, 'xpos'].max()+1)
        ax.set_ylim(0, rank_counts.sum().max())
        ax.set_facecolor('white')

        if group_l0 is None:
            ax.set_ylabel('relative abundance')
        else:
            label = n0
            if no_sample_numbers is False:
                label += "\n(n=%i)" % _get_sample_numbers(
                    num_samples, [group_l0], [n0])
            ax.set_ylabel(label)

        # print labels on top of the groups
        if not no_top_labels:
            if len(graphinfo.loc[g0.index, 'group_l1'].unique()) > 1:
                ax2 = ax.twiny()
                labels = []
                pos = []
                for n, g in graphinfo.loc[g0.index, :].groupby('group_l1'):
                    pos.append(g['xpos'].mean()+0.5)
                    label = str(n)
                    if no_sample_numbers is False:
                        label += "\n(n=%i)" % _get_sample_numbers(
                            num_samples, [group_l0, group_l1], [n0, n])
                    labels.append(label)
                ax2.set_xticks(pos)
                ax2.set_xlim(ax.get_xlim())
                ax2.set_xticklabels(labels)
                ax2.xaxis.set_ticks_position("top")
                ax2.xaxis.grid()

        # print labels for group level 2
        if group_l2 is not None:
            ax3 = ax.twiny()
            ax3.set_xlim(ax.get_xlim())
            pos = []
            labels = []
            poslabel = []
            for n, g in graphinfo.loc[g0.index, :].groupby(['group_l1',
                                                            'group_l2']):
                pos.append(g.sort_values('xpos').iloc[0, :].loc['xpos'])
                poslabel.append(g['xpos'].mean())
                label = str(g.sort_values('xpos').iloc[0, :].loc['group_l2'])
                if no_sample_numbers is False:
                    label += "\n(n=%i)" % _get_sample_numbers(
                        num_samples,
                        [group_l0, group_l1, group_l2],
                        [n0, n[0], n[1]])
                labels.append(label)
            ax3.set_xticks(np.array(poslabel)+.5, minor=False)
            ax3.set_xticks(np.array(pos), minor=True)
            ax3.set_xticklabels(labels, rotation='vertical')
            ax3.xaxis.set_ticks_position("bottom")
            ax3.xaxis.grid(False, which='major')
            ax3.xaxis.grid(True, which='minor', color="black")

        # draw boxes around each group
        if len(graphinfo.loc[g0.index, 'group_l1'].unique()) > 1:
            for n, g in graphinfo.loc[g0.index, :].groupby('group_l1'):
                ax.add_patch(
                    mpatches.Rectangle(
                        (g['xpos'].min(), 0.0),   # (x,y)
                        g['xpos'].max()-g['xpos'].min()+1,          # width
                        1.0,          # height
                        fill=False,
                        edgecolor="gray",
                        linewidth=1,
                    )
                )

        # display a legend
        if ypos == 0:
            l_patches = [mpatches.Patch(color=colors[tax], label=tax)
                         for tax in vals.index
                         if (tax in highAbundantTaxa) |
                            (tax == NAME_LOW_ABUNDANCE)]
            label_low_abundant = "+%i %s taxa" % (len(lowAbundandTaxa),
                                                  NAME_LOW_ABUNDANCE)
            if grayscale:
                l_patches.append(mpatches.Patch(color='gray',
                                                label=label_low_abundant))
            else:
                if l_patches[-1]._label == NAME_LOW_ABUNDANCE:
                    l_patches[-1]._label = label_low_abundant
            ax.legend(handles=l_patches,
                      loc='upper left',
                      bbox_to_anchor=(1.01, 1.05))
            font0 = FontProperties()
            font0.set_weight('bold')
            title = 'Rank: %s' % rank
            if fct_aggregate is not None:
                title = ('Aggregrated "%s"\n' % fct_aggregate.__name__) + title
            ax.get_legend().set_title(title=title, prop=font0)

    if verbose:
        out.write("raw counts: %i\n" % rawcounts.shape[1])
        out.write("raw meta: %i\n" % metadata.shape[0])
        out.write("meta with counts: %i samples x %i fields\n" % meta.shape)
        out.write("counts with meta: %i\n" % rank_counts.shape[1])
        if grayscale:
            out.write("saved plotting %i boxes.\n" % num_saved_boxes)

    return fig, rank_counts, graphinfo, vals, colors


def _time_torque2slurm(t_time):
    """Convertes run-time resource string from Torque to Slurm.
    Input format is hh:mm:ss, output is <days>-<hours>:<minutes>

    Parameters
    ----------
    t_time : str
        Input time duration in format hh:mm:ss

    Returns
    -------
    Slurm compatible time duration.
    """
    t_hours, t_minutes, t_seconds = map(int, t_time.split(':'))
    s_minutes = (t_seconds // 60) + t_minutes
    s_hours = (s_minutes // 60) + t_hours
    s_minutes = s_minutes % 60
    s_days = s_hours // 24
    s_hours = s_hours % 24

    # set a minimal run time, if Torque time is < 60 seconds
    if (s_days == 0) and (s_hours == 0) and (s_minutes == 0):
        s_minutes = 1

    return "%i-%i:%i" % (s_days, s_hours, s_minutes)


def _add_timing_cmds(commands, file_timing):
    """Change list of commands, such that system's time is used to trace
       run-time.

    Parameters
    ----------
    commands : [str]
        List of commands.
    file_timing : str
        Filepath to the file into which timing information shall be written

    Returns
    -------
    [str] list of changed commands with timing capability.
    """
    timing_cmds = []
    # report machine name
    timing_cmds.append('uname -a > %s' % file_timing)
    # report commands to be executed (I have problems with quotes)
    # timing_cmds.append('echo `%s` >> ${PBS_JOBNAME}.t${PBS_JOBID}'
    #                    % '; '.join(cmds))
    # add time to every command
    for cmd in commands:
        # cd cannot be timed and any attempt will fail changing the
        # directory
        if cmd.startswith('cd '):
            timing_cmds.append(cmd)
        else:
            timing_cmds.append(('%s '
                                '-v '
                                '-o %s '
                                '-a %s') %
                               (EXEC_TIME, file_timing, cmd))
    return timing_cmds


def cluster_run(cmds, jobname, result, environment=None,
                walltime='4:00:00', nodes=1, ppn=10, pmem='8GB',
                gebin='/opt/torque-4.2.8/bin', dry=True, wait=False,
                file_qid=None, slurm=False, out=sys.stdout, err=sys.stderr,
                timing=False, file_timing=None, array=1):
    """ Submits a job to the cluster.

    Paramaters
    ----------
    cmds : [str]
        List of commands to be run on the cluster.
    jobname : str
        A name for the cluster job.
    result : path
        A file or dir holding results of a sucessful run. Don't re-submit if
        result exists.
    environment : str
        Name of a conda environment to activate.
    walltime : str
        Format hh:mm:ss maximal CPU time for the job. Default: '4:00:00'.
    nodes : int
        Number of nodes onto the job should be distributed. Defaul: 1
    ppn : int
        Number of cores within one node onto which the job should be
        distributed. Default 10.
    pmem : str
        Format 'xGB'. Memory requirement per ppn for the job, e.g. if ppn=10
        and pmem=8GB the node must have at least 80GB free memory.
        Default: '8GB'.
    gebin : path
        Path to the dir holding SGE binaries.
        Default: /opt/torque-4.2.8/bin
    dry : bool
        Only print command instead of executing it. Good for debugging.
        Default = True
    wait : bool
        Wait for job completion before qsub's return
    file_qid : str
        Default None. Create a file containing the qid of the submitted job.
        This will ease identification of TMP working directories.
    slurm : bool
        Execute cluster job via Slurm instead of Torque.
    out : StringIO
        Buffer onto which messages should be printed. Default is sys.stdout.
    err : StringIO
        Default: sys.stderr.
        Buffer for status reports.
    timing : bool
        If True than add time output to every command and store in cr_*.t*
        file. Default is False.
    file_timing : str
        Default: None
        Define filepath into which timeing information shall be written.
    array : int
        Default: 1
        If > 1 than an array job is submitted. Make sure in- and outputs can
        deal with ${PBS_ARRAYID}!
        Only available for Torque.

    Returns
    -------
    Cluster job ID as str.
    """

    if result is None:
        raise ValueError("You need to specify a result path.")
    parent_res_dir = "/".join(result.split('/')[:-1])
    if not os.access(parent_res_dir, os.W_OK):
        raise ValueError("Parent result directory '%s' is not writable!" %
                         parent_res_dir)
    if file_qid is not None:
        if not os.access('/'.join(file_qid.split('/')[:-1]), os.W_OK):
            raise ValueError("Cannot write qid file '%s'." % file_qid)
    if os.path.exists(result):
        err.write("%s already computed\n" % jobname)
        return "Result already present!"
    if jobname is None:
        raise ValueError("You need to set a jobname!")
    if len(jobname) <= 1:
        raise ValueError("You need to set non empty jobname!")

    if not isinstance(cmds, list):
        cmds = [cmds]
    for cmd in cmds:
        if "'" in cmd:
            raise ValueError("One of your commands contain a ' char. "
                             "Please remove!")
    if timing:
        if file_timing is None:
            file_timing = '${PBS_JOBNAME}.t${PBS_JOBID}'
        cmds = _add_timing_cmds(cmds, file_timing)
    job_cmd = " && ".join(cmds)

    # compose qsub specific details
    pwd = subprocess.check_output(["pwd"]).decode('ascii').rstrip()
    # switch to high mem queue if memory requirement exeeds 250 GB
    highmem = ''
    slurm_script = None
    if slurm is False:
        if ppn * int(pmem[:-2]) > 250:
            highmem = ':highmem'
        ge_cmd = (("%s/qsub -d '%s' -V -l "
                   "walltime=%s,nodes=%i%s:ppn=%i,pmem=%s -N cr_%s -t 1-%i") %
                  (gebin, pwd, walltime, nodes, highmem, ppn, pmem, jobname,
                   array))
        full_cmd = "echo '%s' | %s" % (job_cmd, ge_cmd)
    else:
        slurm_script = "#!/bin/bash\n\n"
        slurm_script += '#SBATCH --job-name=cr_%s\n' % jobname
        slurm_script += '#SBATCH --output=%s/%%A.log\n' % pwd
        slurm_script += '#SBATCH --partition=hii02\n'
        slurm_script += '#SBATCH --ntasks=1\n'
        slurm_script += '#SBATCH --cpus-per-task=%i\n' % ppn
        slurm_script += '#SBATCH --mem-per-cpu=%s\n' % pmem.upper()
        slurm_script += '#SBATCH --time=%s\n' % _time_torque2slurm(walltime)
        slurm_script += '#SBATCH --array=1-%i\n' % array
        slurm_script += '#SBATCH --mail-type=END,FAIL\n'
        slurm_script += '#SBATCH --mail-user=sjanssen@ucsd.edu\n\n'
        slurm_script += 'srun uname -a\n'
        for cmd in cmds:
            slurm_script += 'srun %s\n' % cmd
        full_cmd = ""

    env_present = None
    if environment is not None:
        # check if environment exists
        with subprocess.Popen("conda env list | grep %s -c" % environment,
                              shell=True,
                              stdout=subprocess.PIPE) as env_present:
            if (env_present.wait() != 0):
                raise ValueError("Conda environment '%s' not present." %
                                 environment)
        full_cmd = "source activate %s && %s" % (environment, full_cmd)

    if dry is False:
        if slurm:
            _, file_script = mkstemp(suffix='.slurm.sh')
            f = open(file_script, 'w')
            f.write(slurm_script)
            f.close()
            full_cmd += 'sbatch %s' % file_script
        with subprocess.Popen(full_cmd,
                              shell=True, stdout=subprocess.PIPE) as task_qsub:
            qid = task_qsub.stdout.read().decode('ascii').rstrip()
            if slurm:
                qid = qid.split()[-1]
                os.remove(file_script)
            if file_qid is not None:
                f = open(file_qid, 'w')
                f.write('Cluster job ID is:\n%s\n' % qid)
                f.close()
            job_ever_seen = False
            if wait:
                err.write("\nWaiting for cluster job %s to complete: " % qid)
                while True:
                    if slurm:
                        task_squeue = subprocess.Popen(
                            ['squeue', '--job', qid], stdout=subprocess.PIPE)
                        task_wc = subprocess.Popen(
                            ['wc', '-l'], stdin=task_squeue.stdout,
                            stdout=subprocess.PIPE)
                        poll_status = \
                            int(task_wc.stdout.read().decode('ascii').rstrip())
                        # Two if polling gives a table with header and one
                        # status line, i.e. job is still on the grid.
                        # Translate that to 0 of Torque.
                        # If table has only one line, i.e. the header, job
                        # terminated (hopefully successful), translate that
                        # to 1 of Torque
                        if poll_status == 2:
                            poll_status = 0
                        else:
                            poll_status = 1
                    else:
                        poll_stati = []
                        for i in range(array):
                            p = subprocess.call(
                                "%s/qstat %s" %
                                (gebin, qid.replace('[]', '[%i]' % (i+1))),
                                shell=True)
                            poll_stati.append(p == 0)
                        if any(poll_stati):
                            poll_status = 0
                        else:
                            poll_status = 127  # some number != 0
                    if (poll_status != 0) and job_ever_seen:
                        err.write(' finished.')
                        break
                    elif (poll_status == 0) and (not job_ever_seen):
                        job_ever_seen = True
                    err.write('.')
                    time.sleep(10)
            else:
                err.write("Now wait until %s job finishes.\n" % qid)
            return qid
    else:
        if slurm:
            out.write(slurm_script + "\n")
        out.write(full_cmd + "\n")
        return None


def detect_distant_groups_alpha(alpha, groupings,
                                min_group_size=21):
    """Given metadata field, test for sig. group differences in alpha
       distances.

    Parameters
    ----------
    alpha : pandas.core.series.Series
        The alpha diversities for the samples
    groupings : pandas.core.series.Series
        A group label per sample.
    min_group_size : int
        A minimal group size to be considered. Smaller group labels will be
        ignored. Default: 21.

    Returns
    -------
    dict with following keys:
        network :          a dict of dicts to list for every pair of group
                           labels its 'p-value' and 'avgdist'
        n_per_group :      a pandas.core.series.Series reporting the remaining
                           number of samples per group
        min_group_size :   passes min_group_size
        num_permutations : None
        metric_name :      passes metric_name
        group_name :       passes the name of the grouping
    """
    # remove samples whose grouping in NaN
    groupings = groupings.dropna()

    # remove samples for which we don't have alpha div measures
    groupings = groupings.loc[list(alpha.index)]

    # remove groups with less than minNum samples per group
    groups = sorted([name
                     for name, counts
                     in groupings.value_counts().iteritems()
                     if counts >= min_group_size])

    network = dict()
    for a, b in combinations(groups, 2):
        res = mannwhitneyu(alpha.loc[groupings[groupings == a].index],
                           alpha.loc[groupings[groupings == b].index],
                           alternative='two-sided')

        if a not in network:
            network[a] = dict()
        network[a][b] = {'p-value': res.pvalue,
                         'test-statistic': res.statistic}

    ns = groupings.value_counts()
    return ({'network': network,
             'n_per_group': ns[ns.index.isin(groups)],
             'min_group_size': min_group_size,
             'num_permutations': None,
             'metric_name': alpha.name,
             'group_name': groupings.name})


def detect_distant_groups(beta_dm, metric_name, groupings, min_group_size=5,
                          num_permutations=999):
    """Given metadata field, test for sig. group differences in beta distances.

    Parameters
    ----------
    beta_dm : skbio.stats.distance._base.DistanceMatrix
        The beta diversity distance matrix for the samples
    metric_name : str
        Please provide the metric name used to create beta_dm. This is only
        for visualization purposes.
    groupings : pandas.core.series.Series
        A group label per sample.
    min_group_size : int
        A minimal group size to be considered. Smaller group labels will be
        ignored. Default: 5.
    num_permutations : int
        Number of permutations to use for permanova test.

    Returns
    -------
    dict with following keys:
        network :          a dict of dicts to list for every pair of group
                           labels its 'p-value' and 'avgdist'
        n_per_group :      a pandas.core.series.Series reporting the remaining
                           number of samples per group
        min_group_size :   passes min_group_size
        num_permutations : passes num_permutations
        metric_name :      passes metric_name
        group_name :       passes the name of the grouping
    """

    # remove samples whose grouping in NaN
    groupings = groupings.dropna()

    # remove samples not in the distance matrix
    groupings = groupings.loc[list(beta_dm.ids)]

    # remove groups with less than minNum samples per group
    groups = sorted([name
                     for name, counts
                     in groupings.value_counts().iteritems()
                     if counts >= min_group_size])

    network = dict()
    for a, b in combinations(groups, 2):
        group = groupings[groupings.isin([a, b])]
        group_dm = beta_dm.filter(group.index)
        res = permanova(group_dm, group, permutations=num_permutations)

        if a not in network:
            network[a] = dict()
        network[a][b] = {'p-value': res["p-value"],
                         'test-statistic': res["test statistic"],
                         'avgdist':
                         np.mean([group_dm[x, y]
                                  for x in group[group == a].index
                                  for y in group[group == b].index])}

    ns = groupings.value_counts()
    return ({'network': network,
             'n_per_group': ns[ns.index.isin(groups)],
             'min_group_size': min_group_size,
             'num_permutations': num_permutations,
             'metric_name': metric_name,
             'group_name': groupings.name})


def _getfirstsigdigit(number):
    """Given a float between < 1, determine the position of first non-zero
       digit.
    """
    if number >= 1:
        return 0
    num_digits = 1
    while ('%f' % number).split('.')[1][num_digits-1] == '0':
        num_digits += 1
    return num_digits


def groups_is_significant(group_infos, pthresh=0.05):
    """Checks if a network has significantly different groups.

    Parameters
    ----------
    group_infos : dict()
        result of a detect_distant_groups() run
    pthresh : float
        The maximal p-value of a group difference to be considered significant.
        It will be corrected for multiple hypothesis testing in a naive way,
        i.e. by dividing with number of all pairwise groups.

    Returns
    -------
    Boolean.
    """
    numComp = len(list(combinations(group_infos['n_per_group'].keys(), 2)))
    for a in group_infos['network'].keys():
        for b in group_infos['network'][a].keys():
            if group_infos['network'][a][b]['p-value'] <= pthresh / numComp:
                return True
    return False


def plotDistant_groups(network, n_per_group, min_group_size, num_permutations,
                       metric_name, group_name, pthresh=0.05, _type='beta',
                       draw_edgelabel=False, ax=None):
    """Plots pairwise beta diversity group relations (obtained by
       'detect_distant_groups')

    Parameters
    ----------
    Most parameters are direct outputs of detect_distant_groups, thus you can
    pass **res = detect_distant_groups(...) here
    network : dict
        a dict of dicts to list for every pair of group labels its 'p-value'
        and 'avgdist'
    n_per_group : pandas.core.series.Series
        reporting the remaining number of samples per group
    min_group_size : int
        The minimal group size that was considered.
    num_permutations : int
        Number of permutations used for permanova test.
    metric_name : str
        The beta diversity metric name used.
    group_name : str
        A label for the grouping criterion.
    pthresh : float
        The maximal p-value of a group difference to be considered significant.
        It will be corrected for multiple hypothesis testing in a naive way,
        i.e. by dividing with number of all pairwise groups.
    _type : str
        Default: 'beta'. Choose from 'beta' or 'alpha'. Determines the type of
        diversity that was considered for testing significant group
        differences.
    draw_edgelabel : boolean
        If true, draw p-values as edge labels.
    ax : plt axis
        If not none, use this axis to plot on.

    Returns
    -------
    A matplotlib figure.
    """
    LINEWIDTH_SIG = 2.0
    LINEWIDTH_NONSIG = 0.2
    NODECOLOR = {'alpha': 'lightblue', 'beta': 'lightgreen'}

    # initialize empty graph
    G = nx.Graph()
    # add node for every group to the graph
    G.add_nodes_from(list(n_per_group.index))

    numComp = len(list(combinations(n_per_group.keys(), 2)))

    # add edges between all nodes to the graph
    for a in network.keys():
        for b in network[a].keys():
            weight = LINEWIDTH_NONSIG
            # naive FDR by just dividing p-value by number of groups-pairs
            if network[a][b]['p-value'] <= pthresh / numComp:
                weight = LINEWIDTH_SIG
            G.add_edge(a, b,
                       pvalue="%.2f" % network[a][b]['p-value'],
                       weight=weight)

    # ignore warnings of matplotlib due to outdated networkx calls
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore",
                                category=matplotlib.cbook.mplDeprecation)
        warnings.filterwarnings("ignore",
                                category=UserWarning,
                                module="matplotlib")

        if ax is None:
            fig, ax = plt.subplots(1, 1)

        # use circular graph layout. Spring layout did not really work here.
        pos = nx.circular_layout(G)
        # nodes are randomly assigned to fixed positions, here I re assigned
        # positions by sorted node names to make images determined.
        new_pos = dict()
        l_pos = sorted(list(pos.values()), key=lambda i: i[0] + 1000 * i[1])
        l_nodes = list(sorted(pos.keys()))
        for (key, value) in zip(l_nodes, l_pos):
            new_pos[key] = value
        weights = [G[u][v]['weight'] for u, v in G.edges()]
        nx.draw(G, with_labels=False, pos=new_pos, width=weights,
                node_color=NODECOLOR[_type],
                edge_color='gray',
                ax=ax)

        # draw labels for nodes instead of pure names
        for node in G:
            nx.draw_networkx_labels(
                G, new_pos,
                labels={node: "%s\nn=%i" % (node, n_per_group.loc[node])},
                font_color='black', font_weight='bold',
                ax=ax)

        # draw edge labels
        if draw_edgelabel:
            # ensure that edges are addressed in the same way, i.e. (a, b)
            # is not (b, a): tuple(sorted(...))
            edge_labels = \
                dict([(tuple(sorted((a, b,))), data['pvalue'])
                      for a, b, data
                      in G.edges(data=True)
                      if (float(data['pvalue']) < pthresh / numComp) or
                      (len(network.keys()) < 8)])
            nx.draw_networkx_edge_labels(G, new_pos, edge_labels=edge_labels,
                                         ax=ax, label_pos=0.25)
            # , label_pos=0.5, font_size=10, font_color='k',
            # font_family='sans-serif', font_weight='normal', alpha=1.0,
            # bbox=None, ax=None, rotate=True, **kwds)

        # plot title
        ax.set_title("%s: %s" % (_type, group_name), fontsize=20)
        text = ''
        if _type == 'beta':
            text = 'p-wise permanova\n%i perm., %s' % (num_permutations,
                                                       metric_name)
        elif _type == 'alpha':
            text = 'p-wise two-sided Mann-Whitney\n%s' % metric_name
        ax.text(0.5, 0.98, text, transform=ax.transAxes, ha='center', va='top')

        # plot legend
        ax.plot([0], [0], 'gray',
                label=u'p ≤ %0.*f' % (_getfirstsigdigit(pthresh), pthresh),
                linewidth=LINEWIDTH_SIG)
        ax.plot([0], [0], 'gray',
                label='p > %0.*f' % (_getfirstsigdigit(pthresh), pthresh),
                linewidth=LINEWIDTH_NONSIG)
        ax.legend(title='FDR corrected')

    return ax


def plotGroup_histograms(alpha, groupings, min_group_size=21, ax=None):
    """Plots alpha diversity histograms for grouped data.

    Parameters
    ----------
    alpha : pandas.core.series.Series
        The alpha diversities for the samples
    groupings : pandas.core.series.Series
        A group label per sample.
    min_group_size : int
        A minimal group size to be considered. Smaller group labels will be
        ignored. Default: 21.
    ax : plt axis
        The axis to plot on. If none, create a new plt figure and return.

    Returns
    -------
    A plt axis with histograms for each group.
    """
    # remove samples whose grouping in NaN
    groupings = groupings.dropna()

    # remove samples for which we don't have alpha div measures
    groupings = groupings.loc[list(alpha.index)]

    # remove groups with less than minNum samples per group
    groups = [name
              for name, counts
              in groupings.value_counts().iteritems()
              if counts >= min_group_size]

    if ax is None:
        fig, ax = plt.subplots(1, 1)

    for group in groups:
        sns.distplot(alpha.loc[groupings[groupings == group].index],
                     hist=False, label=group, ax=ax, rug=True)

    return ax


def plotGroup_permanovas(beta, groupings,
                         network, n_per_group, min_group_size,
                         num_permutations, metric_name, group_name,
                         ax=None):
    # remove samples whose grouping in NaN
    groupings = groupings.dropna()

    # remove samples for which we don't have alpha div measures
    groupings = groupings.loc[list(beta.ids)]

    # remove groups with less than minNum samples per group
    groups = sorted([name
                     for name, counts
                     in groupings.value_counts().iteritems()
                     if counts >= min_group_size])

    if ax is None:
        fig, ax = plt.subplots(1, 1)

    if n_per_group.shape[0] < 2:
        ax.text(0.5, 0.5,
                'only %i group:\n"%s"' % (n_per_group.shape[0],
                                          ", ".join(list(n_per_group.index))),
                ha='center', va='center', fontsize=15)
        ax.axis('off')
        return ax

    data = []
    name_left = 'left'
    name_right = 'right'
    name_inter = 'between'
    for a, b in combinations(groups, 2):
        nw = None
        if a in network:
            if b in network[a]:
                nw = network[a][b]
        if (nw is None) & (b in network):
            if a in network[b]:
                nw = network[b][a]

        edgename = 'left:%s\np: %.*f\nright:%s' % (
            a,
            _getfirstsigdigit(nw['p-value']),
            nw['p-value'],
            b)
        dists = dict()
        # intra group distances
        dists[name_left] = [beta[x, y]
                            for x, y in
                            combinations(groupings[groupings == a].index, 2)]
        dists[name_right] = [beta[x, y]
                             for x, y in
                             combinations(groupings[groupings == b].index, 2)]
        # inter group distances
        dists[name_inter] = [beta[x, y]
                             for x in
                             groupings[groupings == a].index
                             for y in
                             groupings[groupings == b].index]

        for _type in dists.keys():
            for d in dists[_type]:
                data.append({'edge': edgename, '_type': _type, metric_name: d})

    colors = ["green", "cyan", "lightblue", "dusty purple", "greyish", ]
    sns.boxplot(data=pd.DataFrame(data),
                x='edge',
                y=metric_name,
                hue='_type',
                hue_order=[name_left, name_inter, name_right],
                ax=ax,
                palette=sns.xkcd_palette(colors))
    ax.legend(bbox_to_anchor=(1.05, 1))
    ax.xaxis.label.set_visible(False)

    return ax


def mutate_sequence(sequence, num_mutations=1,
                    alphabet=['A', 'C', 'G', 'T']):
    """Introduce a number of point mutations to a DNA sequence.

    No position will be mutated more than once.

    Parameters
    ----------
    sequence : str
        The sequence that is going to get mutated.
    num_mutations : int
        Number of mutations that should be made in the sequence.
        Default is 1.
    alphabet : [chars]
        Alphabet of replacement characters for mutations.
        Default is [A,C,G,T], i.e. DNA alphabet. Change to [A,C,G,U] for RNA.

    Returns
    -------
    str : the mutated sequence.

    Raises
    ------
    ValueError:
        a) if number of mutations exceeds available characters in sequence.
        b) if alphabet is so limited that position to be mutated will be the
           same as before.
    """
    if len(sequence) < num_mutations:
        raise ValueError("Sequence not long enough for that many mutations.")
    positions = set(range(0, len(sequence)))
    mutated_positions = set()
    mut_sequence = sequence
    while len(mutated_positions) < num_mutations:
        pos = random.choice(list(positions))
        positions.remove(pos)
        mutated_positions.add(pos)
        cur = mut_sequence[pos].upper()
        replacement_candidates = [c for c in alphabet if c.upper() != cur]
        try:
            mut = random.choice(replacement_candidates)
        except IndexError:
            raise ValueError("Alphabet is too small to find mutation!")
        mut_sequence = mut_sequence[:pos] + mut + mut_sequence[pos+1:]
    return mut_sequence


def cache(func):
    """Decorator: Cache results of a function call to disk.

    Parameters
    ----------
    func : executabale
        A function plus parameters whichs results shall be cached, e.g.
        "fct_example(1,5,3)", where
        @cache
        def fct_test(a, b, c):
            return a + b * c
    cache_filename : str
        Default: None. I.e. caching is deactivated.
        Pathname to cache file, which will hold results of the function call.
        If file exists, results are loaded from it instead of recomputing via
        provided function. Otherwise, function will be executed and results
        stored to this file.
    cache_verbose : bool
        Default: True.
        Report caching status to 'cache_err', which by default is sys.stderr.
    cache_err : StringIO
        Default: sys.stderr.
        Stream onto which status messages shall be printed.
    cache_force_renew : bool
        Default: False.
        Force re-execution of provided function even if cache file exists.

    Returns
    -------
    Results of provided function, either by actually executing the function
    with provided parameters or by loaded results from filename.

    Notes
    -----
    It is the obligation of the user to ensure that arguments for the provided
    function don't change between creation of cache file and loading from cache
    file!
    """
    func_name = func.__name__

    def execute(*args, **kwargs):
        cache_args = {'cache_filename': None,
                      'cache_verbose': True,
                      'cache_err': sys.stderr,
                      'cache_force_renew': False}
        for varname in cache_args.keys():
            if varname in kwargs:
                cache_args[varname] = kwargs[varname]
                del kwargs[varname]

        if cache_args['cache_filename'] is None:
            if cache_args['cache_verbose']:
                cache_args['cache_err'].write(
                    '%s: no caching, since "cache_filename" is None.\n' %
                    func_name)
            return func(*args, **kwargs)

        if os.path.exists(cache_args['cache_filename']) and\
           (os.stat(cache_args['cache_filename']).st_size <= 0):
            if cache_args['cache_verbose']:
                cache_args['cache_err'].write(
                    '%s: removed empty cache.\n' %
                    func_name)
            os.remove(cache_args['cache_filename'])

        if (not os.path.exists(cache_args['cache_filename'])) or\
           cache_args['cache_force_renew']:
            try:
                f = open(cache_args['cache_filename'], 'wb')
                results = func(*args, **kwargs)
                pickle.dump(results, f)
                f.close()
                if cache_args['cache_verbose']:
                    cache_args['cache_err'].write(
                        '%s: stored results in cache "%s".\n' %
                        (func_name, cache_args['cache_filename']))
            except Exception as e:
                raise e
        else:
            f = open(cache_args['cache_filename'], 'rb')
            results = pickle.load(f)
            f.close()
            if cache_args['cache_verbose']:
                cache_args['cache_err'].write(
                    '%s: retrieved results from cache "%s".\n' %
                    (func_name, cache_args['cache_filename']))
        return results
    if func.__doc__ is not None:
        execute.__doc__ = func.__doc__
    else:
        execute.__doc__ = ""
    execute.__doc__ += "\n\n" + cache.__doc__
    # restore wrapped function name
    execute.__name__ = func_name
    return execute


def _map_metadata_calout(metadata, calour_experiment, field):
    """Calour reads a metadata TSV not as dtype=str,
       therefore certain values change :-("""
    _mapped_meta = pd.concat([metadata[field],
                              calour_experiment.sample_metadata[field]],
                             axis=1).dropna()
    _mapped_meta.columns = ['meta', 'calour']
    _map = dict()
    for value_metadata in _mapped_meta['meta'].unique():
        values_calour = _mapped_meta[
            _mapped_meta['meta'] == value_metadata]['calour'].unique()
        if len(values_calour) > 1:
            raise ValueError('More than one value map!!')
        _map[value_metadata] = values_calour[0]
    return _map


def _find_diff_taxa_runpfdr(calour_experiment, metadata, field, diffTaxa=None,
                            out=sys.stdout):
    """Finds differentially abundant taxa in a calour experiment for the given
       metadata field.

    Parameters
    ----------
    calour_experiment : calour.experiment
        The calour experiment, holding the OTU table and all metadata
        information.
    metadata : pd.DataFrame
        metadata for samples. Cannot use calour sample_metadata due to internal
        datatype casts, e.g. int might become floats.
    field : str
        The metadata column along which samples should be separated and tested
        for differentially abundant taxa.
    diffTaxa : dict(dict())
        A prefilled return object, for cases where we want to combine evidence.
    out : StringIO
        The strem onto which messages should be written. Default is sys.stdout.

    Returns
    -------
        A dict of dict. First level key are the pairs of field values between
        which has been tested, second level is the taxon, value is number of
        times this taxon found to be differentially abundant.
    """

    if diffTaxa is None:
        diffTaxa = dict()

    metadata = metadata.loc[calour_experiment.sample_metadata.index, :]

    ns = metadata[field].value_counts()
    e = calour_experiment.filter_ids(metadata.index, axis='s')
    _map_values = _map_metadata_calout(metadata, e, field)
    for (a, b) in combinations(ns.index, 2):
        ediff = e.diff_abundance(field,
                                 _map_values[a],
                                 _map_values[b],
                                 fdr_method='dsfdr')
        out.write("  % 4i taxa different between '%s' (n=%i) vs. '%s' (n=%i)\n"
                  % (ediff.feature_metadata.shape[0], a, ns[a], b, ns[b]))
        if ediff.feature_metadata.shape[0] > 0:
            if (a, b) not in diffTaxa:
                diffTaxa[(a, b)] = dict()
            for taxon in ediff.feature_metadata.index:
                if taxon not in diffTaxa[(a, b)]:
                    diffTaxa[(a, b)][taxon] = 0
                diffTaxa[(a, b)][taxon] += 1

    return diffTaxa


def _find_diff_taxa_singlelevel(calour_experiment, metadata,
                                groups, diffTaxa=None,
                                out=sys.stdout):
    """Finds differentially abundant taxa in a calour experiment for the given
       metadata group of fields, i.e. samples are controlled for the first :-1
       fields and abundance is checked for the latest field.

    Parameters
    ----------
    calour_experiment : calour.experiment
        The calour experiment, holding the OTU table and all metadata
        information.
    metadata : pd.DataFrame
        metadata for samples. Cannot use calour sample_metadata due to internal
        datatype casts, e.g. int might become floats.
    groups : [str]
        The metadata columns for which samples should be controlled (first n-1)
        and along which samples should be separated and tested for
        differentially abundant taxa (last)
    diffTaxa : dict(dict())
        A prefilled return object, for cases where we want to combine evidence.
    out : StringIO
        The strem onto which messages should be written. Default is sys.stdout.

    Returns
    -------
        A dict of dict. First level key are the pairs of field values between
        which has been tested, second level is the taxon, value is number of
        times this taxon found to be differentially abundant.
    """
    if diffTaxa is None:
        diffTaxa = dict()

    metadata = metadata.loc[calour_experiment.sample_metadata.index, :]

    if len(groups) > 1:
        e = calour_experiment.filter_ids(
            metadata.index, inplace=False, axis='s')
        for n, g in metadata.groupby(groups[:-1]):
            name = n
            if type(n) != tuple:
                name = [n]
            out.write(", ".join(
                map(lambda x: "%s: %s" % x, zip(groups, name))) + ", ")
            out.write("'%s'" % groups[-1])
            out.write("  (n=%i)\n" % g.shape[0])

            # filter samples for calour
            e_filtered = e
            for (field, value) in zip(groups, name):
                _map_values = _map_metadata_calout(metadata, e, field)
                if value in _map_values:
                    e_filtered = e_filtered.filter_samples(
                        field, [_map_values[value]], inplace=False)

            diffTaxa = _find_diff_taxa_runpfdr(e_filtered,
                                               metadata,
                                               groups[-1],
                                               diffTaxa)
    else:
        out.write("'%s'" % groups[0])
        out.write("  (n=%i)\n" % metadata.shape[0])
        diffTaxa = _find_diff_taxa_runpfdr(
            calour_experiment, metadata, groups[0], diffTaxa)

    return diffTaxa


def find_diff_taxa(calour_experiment, metadata, groups, diffTaxa=None,
                   out=sys.stdout):
    # TODO: rephrase docstring
    # TODO: unit tests for all three functions
    # TODO: include calour in requirements
    # TODO: fully drag calour into function and pass counts and metadata instea
    """Finds differentially abundant taxa in a calour experiment for the given
       metadata group of fields, i.e. samples are controlled for the first :-1
       fields and abundance is checked for the latest field.

    Parameters
    ----------
    calour_experiment : calour.experiment
        The calour experiment, holding the OTU table and all metadata
        information.
    metadata : pd.DataFrame
        metadata for samples. Cannot use calour sample_metadata due to internal
        datatype casts, e.g. int might become floats.
    groups : [str]
        The metadata columns for which samples should be controlled (first n-1)
        and along which samples should be separated and tested for
        differentially abundant taxa (last)
    diffTaxa : dict(dict())
        A prefilled return object, for cases where we want to combine evidence.
    out : StringIO
        The strem onto which messages should be written. Default is sys.stdout.

    Returns
    -------
        A dict of dict. First level key are the pairs of field values between
        which has been tested, second level is the taxon, value is number of
        times this taxon found to be differentially abundant.
    """
    if diffTaxa is None:
        diffTaxa = dict()

    for i in range(len(groups)):
        sub_groups = groups[len(groups)-i-1:]
        diffTaxa = _find_diff_taxa_singlelevel(
            calour_experiment, metadata, sub_groups, diffTaxa)
        out.write("\n")

    merged_diffTaxa = dict()
    for (a, b) in diffTaxa.keys():
        key = tuple(sorted((a, b)))
        if key not in merged_diffTaxa:
            merged_diffTaxa[key] = dict()
        for feature in diffTaxa[(a, b)].keys():
            if feature not in merged_diffTaxa[key]:
                merged_diffTaxa[key][feature] = 0
            merged_diffTaxa[key][feature] += diffTaxa[(a, b)][feature]

    return merged_diffTaxa


def plot_diff_taxa(counts, metadata_field, diffTaxa, taxonomy=None,
                   min_mean_abundance=0.01):
    """Plots relative abundance and fold change for taxa.

    Parameters
    ----------
    counts : Pandas.DataFrame
        OTU table with rows for features and columns for samples.
    metadata_field : Pandas.Series
        Group labels for every samples between which differentially abundant
        taxa have been found. I.e. one label per sample.
    diffTaxa : dict of dicts
        First level: keys = pairs of group labels
        Second level: keys = feature, values = some numbers (are not considered
        right now)
    taxonomy : Pandas.Series
        Default: none
        Taxonomy labels for features.
    min_mean_abundance : float
        Default: 0.01.
        Minimal relative mean abundance a feature must have in both groups to
        be plotted.

    Returns
    -------
    Matplotlib Figure.
    """
    fig, ax = plt.subplots(len(diffTaxa), 2, figsize=(10, 5*len(diffTaxa)))

    counts.index.name = 'feature'
    relabund = counts / counts.sum()
    comparisons = sorted(map(sorted, diffTaxa.keys()))
    for i, (meta_value_a, meta_value_b) in enumerate(comparisons):
        # only consider taxa given in the diffTaxa object
        taxa = list(diffTaxa[(meta_value_a, meta_value_b)])
        samples_a = metadata_field[metadata_field == meta_value_a].index
        samples_b = metadata_field[metadata_field == meta_value_b].index
        foldchange = np.log((counts.loc[taxa, samples_a]+1).mean(axis=1) /
                            (counts.loc[taxa, samples_b]+1).mean(axis=1))

        # only consider current list of taxa, but now also filter out those
        # with too low relative abundance.
        taxa = sorted(list(
            set([idx
                 for idx, meanabund
                 in relabund.loc[taxa, samples_a].mean(axis=1).iteritems()
                 if meanabund >= min_mean_abundance]) |
            set([idx
                 for idx, meanabund
                 in relabund.loc[taxa, samples_b].mean(axis=1).iteritems()
                 if meanabund >= min_mean_abundance])))
        if len(taxa) <= 0:
            print("Warnings: no taxa left!")

        relabund_field = []
        for (samples, grpname) in [(samples_a, meta_value_a),
                                   (samples_b, meta_value_b)]:
            r = relabund.loc[taxa, samples].stack().reset_index().rename(
                columns={0: 'relative abundance'})
            r['group'] = grpname
            relabund_field.append(r)
        relabund_field = pd.concat(relabund_field)

        curr_ax = ax[0]
        if len(diffTaxa) > 1:
            curr_ax = ax[i][0]
        g = sns.boxplot(data=relabund_field,
                        x='relative abundance',
                        y='feature',
                        order=taxa,
                        hue='group',
                        ax=curr_ax,
                        orient='h')
        g.set_xlim((0, 1))
        curr_ax.legend(loc="upper right")

        curr_ax = ax[1]
        if len(diffTaxa) > 1:
            curr_ax = ax[i][1]
        g = sns.barplot(data=foldchange.loc[taxa].to_frame().reset_index(),
                        orient='h',
                        y='feature',
                        x=0,
                        ax=curr_ax,
                        color=sns.xkcd_rgb["denim blue"])
        g.set_ylabel('')
        if taxonomy is not None:
            g.set(yticklabels=taxonomy.loc[taxa].apply(
                lambda x: " ".join(list(map(str.strip, x.split(';')))[-2:])))

        g.set_xlabel('<-- more in %s     |      more in %s -->' %
                     (meta_value_b, meta_value_a))
        g.yaxis.tick_right()
        g.set_xlim(-1*foldchange.loc[taxa].abs().max(),
                   +1*foldchange.loc[taxa].abs().max())
        fig.suptitle("%s\nminimal relative abundance: %f" %
                     (metadata_field.name, min_mean_abundance))

    return fig
