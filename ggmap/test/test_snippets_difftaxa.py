from unittest import TestCase, main
import pandas as pd
from tempfile import mkstemp
from os import remove

import matplotlib.pyplot as plt
from skbio.util import get_data_path

from ggmap.snippets import (plot_diff_taxa, biom2pandas)
from ggmap.imgdiff import compare_images

plt.switch_backend('Agg')
plt.rc('font', family='DejaVu Sans')


class DiffTaxaTests(TestCase):
    def setUp(self):
        self.diffTaxa = {
            ('Bean', 'Control'):
            {'AAACATAGTGGCCGTAGGTC94': 1,
             'AAAGCCCGATAACGGATAAT216': 1,
             'AAATGCGGAATTGGATCTCG157': 1,
             'AACAGATGTGGAATATTGTT125': 1,
             'AACGGGAGAAGATAAGTAGC233': 1,
             'AACTACTATGATGGTTTTGG61': 1,
             'AACTGTGATAGGCTGGGCCC183': 1,
             'AAGAGGTCTTAGTGTGATTT142': 1,
             'AAGAGTGCGCGGAGAGGGCA104': 1,
             'AATAAAGGTTCATACTTGGA222': 1,
             'AATAATGAATAACTGCTTGT189': 1,
             'AATAGTTTAGTTTCGAAACT77': 1,
             'AATCGAACACTGGTGGCTGG165': 1,
             'AATGGCTAACAGGATAGGAT126': 1,
             'AATTAGGTACGTGGGAGTCC67': 1,
             'AATTATGAAAGGTGTAATGT53': 1,
             'ACACGCAGATTATACCCGTG8': 1,
             'ACATGAATCGGGGCAAACAG153': 1,
             'ACATGGGTCCACACGCAGTA43': 1,
             'ACGAGTACGGTAAGGATAAG185': 1,
             'ACGATGAATCGATAGATTTG106': 1,
             'ACGGAATGCTGGTCGGGTGG74': 1,
             'ACGTGTGAGATGGCATTGGA214': 1,
             'ACTCACTCGTTCATACGGCA234': 1,
             'AGAACCGGCATCACTAATGC120': 1,
             'AGAATCCGAAGGTGGTCCCC161': 1,
             'AGCCGGGGGGAGTCAGGACG68': 1,
             'AGCTAGGCCGACCAGCCTAA19': 1,
             'AGGCATCGATCACGACAGGA186': 1,
             'AGGGGAGGTAGGCATCGGTG63': 1,
             'AGGGTAACAAAAAGCCAGTT22': 1,
             'AGGTTGTGAGAGCAGAATAG41': 1,
             'AGTAGAGGGAAGAGGGGATT148': 1,
             'AGTAGCAGATTAGGGAGGAT50': 1,
             'AGTATCGTTGGGTCATTGCT13': 1,
             'AGTCTGAATGAATGGTGACG173': 1,
             'AGTGGTAGTCTGGCTGCGGG97': 1,
             'AGTGGTCGCTGGTCGGAAAG101': 1,
             'ATACAGGTCATTGAACTGAA196': 1,
             'ATATTAGGAGGTTGGTTTCG211': 1,
             'ATGGGCAATTGGGGCCGTCC42': 1,
             'ATGTGGATTTAGGAGAAGTG5': 1,
             'ATTAAGGTGAGGTCTAGGGG223': 1,
             'ATTCAAAGACTTCCAAGAAG228': 1,
             'ATTGACACCTAATAGAGAAG225': 1,
             'ATTGCGGTAGGTTGGTCCGC37': 1,
             'CAAAGGAGTCGGCGACGTTG54': 1,
             'CAAGCATAAACGTGCTGGAG48': 1,
             'CAGTTCTATGCGTTCTTAGT49': 1,
             'CCATGTTGATTGGTGGGTTG115': 1,
             'CCCCGTGCAGGTTTAGATCC133': 1,
             'CCGATGTAGGGTGACATTTG24': 1,
             'CCGTGTGGTGCTATAAAGCG39': 1,
             'CCGTTCCGCGTTGGAGAGGA21': 1,
             'CCTGCGAAGCCGCCAGCGAT105': 1,
             'CCTTACGATTGATAAAGGTA112': 1,
             'CGACGCTCGACGTCGCTCGG166': 1,
             'CGAGTCAATAGAATTTGACC100': 1,
             'CGATATGGTCCGATATGTGG129': 1,
             'CGGGGATATCGTGGGGCGCT93': 1,
             'CGGTTTCCTGGGACACCCCG60': 1,
             'CGTGAAGAAGACCGACAGCC155': 1,
             'CGTGCGGGCGCGGCCCGAGA15': 1,
             'CGTGCTAGTGGCTCTGCTTC86': 1,
             'CGTGGTGAGTAGGAGAGGAT70': 1,
             'CGTGTGGCGACAGGGGTTAG159': 1,
             'CGTTAGCACCACCTTTCTTG55': 1,
             'CGTTCCTACGGTAAGCAGAA178': 1,
             'CTAAACCGGGAGTTGGCGCG187': 1,
             'CTAGTAGAAGTGATGCTGTA128': 1,
             'CTAGTCGGGATAGAGGTCAG26': 1,
             'CTATTCCAAATTCGAGGGCT180': 1,
             'CTCGATGTCTACCTTATTAT3': 1,
             'CTCGGTGTGCTAGGGTGTAC25': 1,
             'CTGGACGAAGTGCCAGGTTC92': 1,
             'GAAAAACAAGGTGTTTGGCT231': 1,
             'GACATGATAGTAGCTGCGGG89': 1,
             'GACGCCGTATAAACGGGCAT88': 1,
             'GACGTGCAGCGTGTTAATGC184': 1,
             'GAGATATGTTGGGTTTGAAC150': 1,
             'GAGATTCGCGGTTTAAGATC95': 1,
             'GAGGAGAGGGTACCCCAGGC33': 1,
             'GAGGTGTCCTGGCAGTGGTC197': 1,
             'GATAAGGGAGAGTCAGGGAG175': 1,
             'GATATCATTGATGCCCAAGC65': 1,
             'GATTGGTATCGAAGTTGGCG151': 1,
             'GCAATCTTGGGTGGGGAGCC14': 1,
             'GCAGTAATTAGAAGTGCGAC152': 1,
             'GCAGTTCGATTGGACGAAGA131': 1,
             'GCATCGTGAAGAGAGACTTG147': 1,
             'GCATGCTTCAGTGGAGTGCA23': 1,
             'GCCCTAGGCACTTAGAGGGA111': 1,
             'GCGAACTGCGAGAATATGGC116': 1,
             'GCGCAGAGGAAAGAGGAGGC10': 1,
             'GCGGAGATAGTGCGCTATCA28': 1,
             'GCGTTTCCAGTCATTACAGC109': 1,
             'GCTAATGATGAAGCAAGACG134': 1,
             'GCTAGGTAATTGCATGGGTA138': 1,
             'GCTGAGCGGGGTTTCGTTGC140': 1,
             'GCTTACTTCCCCGATGGGTG18': 1,
             'GGAGACGGACCACGTCAGGG9': 1,
             'GGAGCCGATAACAGATGTGA107': 1,
             'GGAGGACTCGCTCGGGCCTA96': 1,
             'GGCACATGTCTGCTGAAAGT170': 1,
             'GGCGTTAGGTATGGTTAGAG182': 1,
             'GGGACACCGTATAGGGAATC224': 1,
             'GGGACGTCGTTGTTAGGTCT144': 1,
             'GGGATTAGGATCAATGACTC227': 1,
             'GGGGAGGGGTGATGAGGGAT113': 1,
             'GGGGTGTGCACGGCGATCGC29': 1,
             'GGGGTTGAATAAGCCAGGAA158': 1,
             'GGTACGCACGTGTACCGGAG108': 1,
             'GGTCAACGGGGAAGAGCAAC199': 1,
             'GGTGACTGCTTGGCGGCTAG194': 1,
             'GGTTAGTAAAAGGGTAAGAA179': 1,
             'GGTTAGTTATACTCGTTGTG149': 1,
             'GTACGAGCGATGAACTATCA154': 1,
             'GTAGGGAAGCGTGCGCGTCG210': 1,
             'GTAGTTGGTTGCTGGACACA215': 1,
             'GTATGGTTCTAGGTTTGGCA204': 1,
             'GTATTGAGGGAAAGTGCAGT66': 1,
             'GTCACGGATTATGCAGGGTA11': 1,
             'GTCGTAAACTTGGGAAGAGG207': 1,
             'GTCTAACCATTATGGCTCAC52': 1,
             'GTCTACGAGTCCGGGAGCTC2': 1,
             'GTCTGGGCCTGGAACAGTAC91': 1,
             'GTGACGGGCGATGCAGCGAG219': 1,
             'GTGCTTTCCCGACGGGTAGG6': 1,
             'GTGGCTTAAGAGGGTGCAAT71': 1,
             'GTTGAGGGGGGCGTCGGAGA99': 1,
             'TAAAACCCCCGCGTTGATCG171': 1,
             'TAAAGTATAGGCGGTTTAGT20': 1,
             'TAAGTGGGGAAATTCCCGCT44': 1,
             'TACAGGGAGATAATACTGAA80': 1,
             'TACTGTATGGCCATGGATAA164': 1,
             'TAGCGCTACACGCAGGGGAT40': 1,
             'TAGGCGGTGCTAAGGCATAT118': 1,
             'TAGTCCGGTGTCGTGGGAAC82': 1,
             'TAGTTCCGCATTACGGCGGC73': 1,
             'TAGTTGCGGAGCCGTTGCCA122': 1,
             'TATCTGCTCATTCATTTAAG198': 1,
             'TATGGGCTAAGGCCATTGTA79': 1,
             'TCCGCAAAGCAGAGAAGGGG218': 1,
             'TCCGGTGCAAGGGTGCGCGG72': 1,
             'TCGGCGCTTTCTGTCTCCTG76': 1,
             'TCGTACAGTGTAGGTGACCC190': 1,
             'TCGTGAGGTCTGACATGTGA135': 1,
             'TGAGGTTGATGAGTACGATT34': 1,
             'TGATAGCTGCGGTCCGGTGG156': 1,
             'TGATGAGCTCGTGTTTGAGG209': 1,
             'TGATTCGAACGCATGTTCGC205': 1,
             'TGCAGATGTGGGCGCCCCCG229': 1,
             'TGCTGTGTAGTCAGTCTGCG143': 1,
             'TGGAGCCTCGGGATACGCTG58': 1,
             'TGGATGGTTCCTATAGAGAG69': 1,
             'TGGTCGGTAGATGTGCAAAG160': 1,
             'TGTCCCGCGCCAGCGGGTGC90': 1,
             'TTAACTGGTCGATGTATGTA1': 1,
             'TTAAGCGATTAAAGTGCGAA230': 1,
             'TTACCTCAGCTCGTGTGCTT203': 1,
             'TTCCAGCCGAGTATGTGTTC64': 1,
             'TTGAACTGGGTGTATCATGT30': 1,
             'TTGAATGGGGAGCACATTGT16': 1,
             'TTGCTGAGGGTGTCCGGGAA177': 1,
             'TTGGATGAGGCCGTTTGGAA78': 1,
             'TTGTCATCTCTAAGGCCACT119': 1,
             'TTGTTGGCGTCGACGCGTAA123': 1,
             'TTTAAGCGTTATTGTTCCGG188': 1,
             'TTTCGGGCGGTCGGTAGTAG121': 1,
             'TTTGTAAGTGCGGGCTGTGA206': 1,
             'TTTTGATAAAACGGGGGTCA75': 1},
            ('Bean', 'Cowpea'):
            {'AAATGACTCTCCTGTTTATG127': 1,
             'AACGCGGACCGGGGCCTGGA132': 1,
             'AACTACTATGATGGTTTTGG61': 1,
             'AATAGTTAGGAGCGAGTAGT7': 1,
             'AATCGAACACTGGTGGCTGG165': 1,
             'AATTAAGGGACTGAATCACG117': 1,
             'AATTATGAAAGGTGTAATGT53': 1,
             'ACGCAAATAGGAATACCACC98': 1,
             'AGAATCCGAAGGTGGTCCCC161': 1,
             'AGATGGTGGGGAGCATGGTG81': 1,
             'AGCCGGGGGGAGTCAGGACG68': 1,
             'AGGCATCGATCACGACAGGA186': 1,
             'AGGGGGACGGAGACGCGTGG17': 1,
             'AGTAGCAGATTAGGGAGGAT50': 1,
             'AGTATCGTTGGGTCATTGCT13': 1,
             'AGTCTGAATGAATGGTGACG173': 1,
             'AGTGAATGAACAGATAAGTA87': 1,
             'AGTGGTAGTCTGGCTGCGGG97': 1,
             'ATCCCAGCCGTTGGCGCTGG200': 1,
             'ATGTGGATTTAGGAGAAGTG5': 1,
             'ATTGCGGTAGGTTGGTCCGC37': 1,
             'CACCTAGTGGGCACTGGGTT145': 1,
             'CCATGTTGATTGGTGGGTTG115': 1,
             'CCCGGGCTGCCGCGCGGGCG38': 1,
             'CCGTCTACGGCGATGGGTTG103': 1,
             'CCGTGTGGTGCTATAAAGCG39': 1,
             'CGCGTAGGTCGCTAAGAACT130': 1,
             'CGGTTTCCTGGGACACCCCG60': 1,
             'CGTGCGGGCGCGGCCCGAGA15': 1,
             'CGTGGTGAGTAGGAGAGGAT70': 1,
             'CGTTCCTACGGTAAGCAGAA178': 1,
             'CTATTCCAAATTCGAGGGCT180': 1,
             'CTGGAGATTGGTAGATAGAT193': 1,
             'CTGTTCTCGGGGATCGCGGG167': 1,
             'GACATGATAGTAGCTGCGGG89': 1,
             'GACGTGCAGCGTGTTAATGC184': 1,
             'GAGCTGGTTATGCCCTGACT220': 1,
             'GAGGGAATCAAAGTCGAGCT136': 1,
             'GAGGTGTCCTGGCAGTGGTC197': 1,
             'GAGTTACGTCCAGAAGGTAC226': 1,
             'GCAGTTCGATTGGACGAAGA131': 1,
             'GCCCGTCGAACGTCGATATG191': 1,
             'GCGAATCTGATCGTACAGTC4': 1,
             'GCTAATGATGAAGCAAGACG134': 1,
             'GCTGGGAGTGTATACCCGGA56': 1,
             'GGCCTATAGCAGAGATTCAT110': 1,
             'GGCGTTAGGTATGGTTAGAG182': 1,
             'GGCTCTCATGCGGTTAACGA208': 1,
             'GGGACACCGTATAGGGAATC224': 1,
             'GGGCTGTCGAGGGTATAGTG212': 1,
             'GGGGCGGTTAAGGTATGAAA57': 1,
             'GGGGGGATGAGGGTCGTAGC62': 1,
             'GGGGTCAGGCAGAGGCAGTA47': 1,
             'GGTAACATGGTGCCTGGGGG213': 1,
             'GGTACGCACGTGTACCGGAG108': 1,
             'GGTTAGTTATACTCGTTGTG149': 1,
             'GTAGTTGGTTGCTGGACACA215': 1,
             'GTATGATATCAGGTATTAAG195': 1,
             'GTTGAGGGGGGCGTCGGAGA99': 1,
             'TAAAATTACGGTGGTAAGTA139': 1,
             'TAGGATCGTTTGAGATGTTG59': 1,
             'TAGTCCGGTGTCGTGGGAAC82': 1,
             'TATCTGCTCATTCATTTAAG198': 1,
             'TCATGAGGATGGACCTTGCC114': 1,
             'TCGTGAGGTCTGACATGTGA135': 1,
             'TGAACAGAATGGGCGGGGAG31': 1,
             'TGAACGATCGAGATTGGTAC141': 1,
             'TGATGAGCTCGTGTTTGAGG209': 1,
             'TGCAGATGTGGGCGCCCCCG229': 1,
             'TGGAGCCTCGGGATACGCTG58': 1,
             'TGGGACCGTGCCTGATATCG102': 1,
             'TTAAGCGATTAAAGTGCGAA230': 1,
             'TTAGAGCTCCCAAGAAAACG202': 1,
             'TTCCAGCCGAGTATGTGTTC64': 1,
             'TTCGGAGCTGTGCTTAGTGT169': 1,
             'TTTCGGGCGGTCGGTAGTAG121': 1},
            ('Control', 'Cowpea'):
            {'AAATGACTCTCCTGTTTATG127': 1,
             'AAATGCGGAATTGGATCTCG157': 1,
             'AACGGGAGAAGATAAGTAGC233': 1,
             'AACTACTATGATGGTTTTGG61': 1,
             'AACTGTGATAGGCTGGGCCC183': 1,
             'AATCGAACACTGGTGGCTGG165': 1,
             'AATTAGGTACGTGGGAGTCC67': 1,
             'AATTATGAAAGGTGTAATGT53': 1,
             'ACATGGGTCCACACGCAGTA43': 1,
             'ACATGGTCGGGGAGTAGATT51': 1,
             'ACGATGAATCGATAGATTTG106': 1,
             'ACGCAAATAGGAATACCACC98': 1,
             'ACGGAGATCCTGAACGGGGG201': 1,
             'AGAATCCGAAGGTGGTCCCC161': 1,
             'AGCCGGGGGGAGTCAGGACG68': 1,
             'AGCTAGGCCGACCAGCCTAA19': 1,
             'AGGATGAAAATGAAGATTTG45': 1,
             'AGGGGGACGGAGACGCGTGG17': 1,
             'AGGTTGTGAGAGCAGAATAG41': 1,
             'AGTAGCAGATTAGGGAGGAT50': 1,
             'AGTCTGAATGAATGGTGACG173': 1,
             'AGTGGTAGTCTGGCTGCGGG97': 1,
             'ATAAGCTGGGGACATAGTTG137': 1,
             'ATGCGGTTGCGCCCCGCTGC32': 1,
             'ATGTGGATTTAGGAGAAGTG5': 1,
             'ATTAAGGTGAGGTCTAGGGG223': 1,
             'ATTGCGGTAGGTTGGTCCGC37': 1,
             'ATTTGTGTAGACCCAAAGGG181': 1,
             'CAAGCATAAACGTGCTGGAG48': 1,
             'CCATGTTGATTGGTGGGTTG115': 1,
             'CCCGGGTACTAGAGTGCATA0': 1,
             'CCGGCTATCGAGTGCTGGGG85': 1,
             'CCGGTCCACACGAGCCCGCA221': 1,
             'CCGTGTGGTGCTATAAAGCG39': 1,
             'CCTGCGAAGCCGCCAGCGAT105': 1,
             'CGAGTCAATAGAATTTGACC100': 1,
             'CGATATGGTCCGATATGTGG129': 1,
             'CGCGTAGGTCGCTAAGAACT130': 1,
             'CGGACCTGATGGACACCGTG27': 1,
             'CGGGCGCGGTGTCGTAAATA172': 1,
             'CGTGCGGGCGCGGCCCGAGA15': 1,
             'CTCTTTCGAAGACAGAGGGA174': 1,
             'CTGGAGATTGGTAGATAGAT193': 1,
             'GAAAACTTGTAATATGGTGT162': 1,
             'GAAGCGATGGTTGGAGGCAA232': 1,
             'GACATGATAGTAGCTGCGGG89': 1,
             'GACGCCGTATAAACGGGCAT88': 1,
             'GAGATATGTTGGGTTTGAAC150': 1,
             'GAGATTCGCGGTTTAAGATC95': 1,
             'GAGGAGAGGGTACCCCAGGC33': 1,
             'GAGGTGTCCTGGCAGTGGTC197': 1,
             'GAGTTACGTCCAGAAGGTAC226': 1,
             'GCAGTCTTAGGGGGGGTTGT46': 1,
             'GCATGGAGCACTCCAGATTA124': 1,
             'GCCCGTCGAACGTCGATATG191': 1,
             'GCCCTAGGCACTTAGAGGGA111': 1,
             'GCGAACTGCGAGAATATGGC116': 1,
             'GCGCAGAGGAAAGAGGAGGC10': 1,
             'GCGTGAGTCGAGAATAAGGA35': 1,
             'GCTAATGATGAAGCAAGACG134': 1,
             'GCTGGGAGTGTATACCCGGA56': 1,
             'GGCACATGTCTGCTGAAAGT170': 1,
             'GGCCTATAGCAGAGATTCAT110': 1,
             'GGCGTTAGGTATGGTTAGAG182': 1,
             'GGGACGTCGTTGTTAGGTCT144': 1,
             'GGGATTAGGATCAATGACTC227': 1,
             'GGGGCGGTTAAGGTATGAAA57': 1,
             'GGGGTCAGGCAGAGGCAGTA47': 1,
             'GGGGTTGAATAAGCCAGGAA158': 1,
             'GGGTTTGAAGAGATAGGAAT83': 1,
             'GGTAACATGGTGCCTGGGGG213': 1,
             'GGTACGCACGTGTACCGGAG108': 1,
             'GGTTAGGGGAGACTGTACTC163': 1,
             'GGTTAGTTATACTCGTTGTG149': 1,
             'GGTTTAGGCTAATTAACTAC192': 1,
             'GTAGTTGGTTGCTGGACACA215': 1,
             'GTATGATATCAGGTATTAAG195': 1,
             'GTATGGGCGCATGGGTAAAA217': 1,
             'GTCACGGATTATGCAGGGTA11': 1,
             'GTGGGGATGTAGGCGGTCGA12': 1,
             'GTTGAGGGGGGCGTCGGAGA99': 1,
             'TAAAACCCCCGCGTTGATCG171': 1,
             'TAAGTGGGGAAATTCCCGCT44': 1,
             'TAATTGCGACTTTACGTCCG84': 1,
             'TACAGGGAGATAATACTGAA80': 1,
             'TAGGCTGTTCGCAAACCGTA176': 1,
             'TAGGTCGAGAACCCGTGTGT146': 1,
             'TAGTCCGGTGTCGTGGGAAC82': 1,
             'TATCTGCTCATTCATTTAAG198': 1,
             'TGATGAGCTCGTGTTTGAGG209': 1,
             'TGCAATAGCAAAGGGGTAAG168': 1,
             'TGGAGCCTCGGGATACGCTG58': 1,
             'TGGGACCGTGCCTGATATCG102': 1,
             'TGGGGGAATGCCCGAACATG36': 1,
             'TGGTCGGTAGATGTGCAAAG160': 1,
             'TTACCTCAGCTCGTGTGCTT203': 1,
             'TTAGAGCTCCCAAGAAAACG202': 1,
             'TTCCAGCCGAGTATGTGTTC64': 1,
             'TTGCTGAGGGTGTCCGGGAA177': 1,
             'TTTCGGGCGGTCGGTAGTAG121': 1,
             'TTTGTAAGTGCGGGCTGTGA206': 1}}
        self.counts = biom2pandas(get_data_path('diffAbundance/counts.biom'))
        self.taxonomy = pd.read_csv(
            get_data_path('diffAbundance/taxonomy.tsv'),
            sep='\t', index_col=0, header=None).iloc[:, 0]
        self.metadata = pd.read_csv(
            get_data_path('diffAbundance/metadata.tsv'), sep='\t', index_col=0)

    def test_plot_diff_taxa(self):
        f = plot_diff_taxa(self.counts,
                           self.metadata['intervention'],
                           self.diffTaxa,
                           self.taxonomy,
                           min_mean_abundance=0.05)
        file_dummy = mkstemp('.png')[1]
        f.savefig(file_dummy, bbox_inches='tight')
        res = compare_images(
            get_data_path('diffAbundance/plot_difftaxa.png'),
            file_dummy,
            file_image_diff='./diff.diffAbundance.plot_difftaxa.png')
        if res[0] is True:
            remove(file_dummy)
        return res[0]


if __name__ == '__main__':
    main()
