"""SCAR 概念词类型词典（全量 1946 词，逐词人工判定）。

判定依据：T01-vocabulary.json 的 τ_V discriminator
  entity            能指到/摸到的具体对象（人、地、机构、器物、生物体）
  substance         被消耗/转化的材料（原料/产物/燃料/试剂/流体）
  process           动作或正在发生的事（含 -ing/-tion 指事件）
  property          特征/数值/状态/关系量
  force             力或连接机制
  abstract_concept  不占空间、承载意义（规则/制度/概念/方法/学科）

逐词判定，不用自动规则。写法：一行一词 TAB 类型。
"""

import textwrap

LEXICON = {}

_PAIRS = """
"""


def _load(block):
    for line in textwrap.dedent(block).strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" not in line:
            raise ValueError(f"缺类型: {line!r}")
        w, t = line.rsplit("\t", 1)
        w = " ".join(w.strip().lower().split())
        t = t.strip()
        if t not in ("entity", "substance", "process", "property", "force",
                     "abstract_concept"):
            raise ValueError(f"非法类型 {t!r} 于 {w!r}")
        LEXICON[w] = t


_load("""
building	entity
biology	abstract_concept
blossom	process
bourgeois revolution	process
blood	substance
bourgeois democratic republic	abstract_concept
bourgeois reform movement	process
bourgeois reformers	entity
bourgeois revolutionaries	entity
bourgeois revolutionary movement	process
brain	entity
british parliament	entity
buddhism	abstract_concept
bacteria	entity
ball	entity
base	substance
battle	process
bible	abstract_concept
bloom	process
body	entity
bone	entity
books	entity
breakwater	entity
brick	entity
bridge	entity
bucket	entity
building materials	substance
building structure	abstract_concept
business	process
businessman	entity
buyer	entity
background	abstract_concept
baird	entity
baker	entity
balance sheet	abstract_concept
balloon	entity
balloon bag	entity
balls	entity
bank	entity
barrier	entity
base pair	entity
basic material	substance
basket	entity
basketball	entity
battlefield	entity
battleground	entity
beam and column	entity
beast	entity
bee	entity
beginning	process
behavior	process
belief	abstract_concept
believer	entity
benefactor	entity
bet	process
beyond the difficulties	abstract_concept
big brother government	entity
bill of rights	abstract_concept
billiards	entity
biochemical reaction	process
biodiversity	property
biological group	entity
biological interactions	process
biological period	property
biological population	entity
biological species	entity
biscuit	entity
biscuit mold	entity
black paint	substance
black slavery	abstract_concept
block	entity
blood cells	entity
blood circulation system	entity
blood sugar	substance
boat	entity
book type	abstract_concept
bookshelf	entity
boom period	process
bottle	entity
bottom of slope	entity
bouncing	process
bourgeois reform	process
bourgeoisie	entity
boxer	entity
bracket	entity
brain waves	property
branch execution	abstract_concept
branch road	entity
branches and leaves	entity
bread	entity
break even	process
breakdown	process
breakfast	entity
breathe	process
breathing	process
breathing muscles	entity
breeding	process
breeds	entity
bricks	entity
bright	property
british colonial rule	abstract_concept
broken	property
bud	entity
budget	property
buendia family	entity
bug	entity
building damage	property
building frame	abstract_concept
building transformation	process
buildings	entity
bullet	entity
bullseye	entity
bureaucracy	abstract_concept
burner	entity
burning	process
buying	process
""")

_load("""
cell	entity
computer	entity
citizen	entity
cuneiform	abstract_concept
charge	property
chemical reaction	process
circuit	entity
crime	abstract_concept
capitalist economy	abstract_concept
cell membrane	entity
cell organelle	entity
chen duxiu	entity
christianity	abstract_concept
collaboration	process
competition	process
conference	process
constitutional convention	abstract_concept
constitutional convention in philadelphia	abstract_concept
container	entity
cooking	process
cpu	entity
create a constitutional monarchy	process
currency	substance
cake	entity
campaign	process
cao xueqin	entity
catalyst	substance
cement	substance
chef	entity
chemical bond	abstract_concept
chlorophyll	substance
chord	entity
client	entity
coach	entity
code	abstract_concept
code of hammurabi	abstract_concept
cold	property
colonial ruling	abstract_concept
columbus	entity
combustion	process
combustion chamber	entity
communication	process
concept	abstract_concept
congress	entity
conservation of energy	abstract_concept
constitutional monarchy	abstract_concept
consumer	entity
control	process
country president	entity
cabinet	entity
cache data	substance
cache hit rate	property
cache size	property
caching algorithm	abstract_concept
cage	entity
calculation process	process
calculation results	property
calm	property
camber	property
campaigning	process
cao yu	entity
capacitance	property
capacity	property
capital	substance
captain	entity
capture	process
car exhaust	substance
carbon dioxide	substance
career	abstract_concept
cargo placement rules	abstract_concept
cell differentiation	process
cell division	process
center	entity
cerebral cortex	entity
challenger	entity
changes	process
chapter	entity
character	abstract_concept
character image	entity
charge flow conservation	abstract_concept
charge force	force
cheap	property
check for phrases	abstract_concept
check in hotel	process
chemical element	substance
chemical formula	abstract_concept
chemical properties	property
chemical reaction heat	property
chemicals	substance
chen bailu	entity
child	entity
children	entity
china	entity
chiral center	entity
chloroplast	entity
choroid	entity
chris mccandless	entity
chromosome	entity
ciphertext	substance
circulatory system	entity
citizens	entity
city	entity
city chaos	property
city on board	entity
city wall	entity
civilian	entity
civilization	abstract_concept
claim	abstract_concept
clark family	entity
clean	process
clear	property
climate change	process
climb	process
climber	entity
clue	abstract_concept
code language	abstract_concept
coding	process
coefficient	property
coffee	substance
cognitive ability	property
collision force	force
color	property
column	entity
combatant	entity
combination	process
combustibles	substance
command	abstract_concept
commemorate	process
commerce	process
commitment	abstract_concept
communication channel	entity
communication line	entity
companion	entity
comparison	process
competitor	entity
complacency	property
complicated	property
components	entity
comprehension	process
computer node	entity
computer system	entity
conclusion	abstract_concept
conditions for the enzyme to work	abstract_concept
conductor	entity
cone	entity
confirm	process
confirming	process
conformance	property
confused	property
confusion	property
congregation	entity
congress	entity
conjecture	abstract_concept
connector	entity
consanguineous marriage	abstract_concept
console	entity
construction	process
construction site	entity
consume	process
contact frequency	property
contest	process
contextual connection	abstract_concept
controller	entity
conversation	process
convex	property
conveyor pipeline	entity
cooking method	abstract_concept
cooking methods	abstract_concept
cooking process	process
cooling	process
copolymer	substance
copper	substance
copy	entity
cornea	entity
correct	property
corruption	process
cosmetic	substance
courtesan	entity
courtship	process
cover	entity
crack	entity
crashing	process
crater	entity
crease	entity
creativity	property
crew	entity
criminal	entity
crisis	process
crispr-cas9 technology	abstract_concept
critic	entity
criticize	process
criticizer	entity
criticizes	process
cromwell	entity
crowd	entity
crowd density	property
crust	entity
crystal structure	abstract_concept
crystalline lens	entity
cui yingying	entity
cultural relics	entity
cultural, political, economic changes	process
cure	process
curiosity	property
cytoplasm	substance
""")

_load("""
data	substance
destination	entity
disease	process
democratic republic	abstract_concept
democratic science	abstract_concept
democrats	entity
dishes	entity
dna	substance
da gama	entity
data point	entity
debater	entity
decision making	process
decorate	process
defeat	process
destroy	process
develop	process
diamond sutra	abstract_concept
dias	entity
dinner	entity
director	entity
divorce	process
dna sequence	substance
doctor	entity
document	entity
dose	property
driving	process
drug	substance
dumas	entity
daily necessities	entity
damage	property
damaged tissue	entity
dance steps	abstract_concept
dante	entity
darkness	property
data line	entity
data relationship	abstract_concept
data sheet	entity
data transmission	process
database table	abstract_concept
dawn	property
daytime	property
death	process
debugging	process
debugging process	process
debugging tool	entity
decision tree	abstract_concept
declaration of independence	abstract_concept
decline	process
decoration	substance
decoration details	abstract_concept
decoration style	abstract_concept
deep learning	process
defend	process
defense	process
degenerate	property
degradation	process
degree of exposure	property
delete operation	process
delicacies	entity
demolition object	entity
deployment	process
descent	process
desertification	process
design	process
design drawings	abstract_concept
destination ip	entity
destiny	abstract_concept
detective	entity
detective tool	entity
detector	entity
deviation	property
devour	process
diagnosis	process
diaphragm	entity
differentiable function	abstract_concept
difficulties	property
difficulty	property
diffusion	process
diffusion medium	substance
digestion	process
digital currency	substance
digresses	process
dim	property
dimensionality reduction	process
diners	entity
disassembly action	process
discovery	process
discriminator	entity
discussion on human nature	process
dish name	abstract_concept
disobedience	process
displacement	property
dissipation	process
distance	property
dna strand	entity
documents	entity
domesticated	property
dominoes	entity
doomed	property
door	entity
dough	substance
down direction	property
drawer	entity
dream catcher	entity
driver	entity
dry skin	substance
dubious	property
duration	property
dust	substance
dying	process
dynamo	entity
dystopia	abstract_concept
""")

_load("""
energy	property
election	process
electric signal	property
ear	entity
ecosystem	entity
electric wire	entity
electronic	property
element	substance
emperor	entity
equal rights	abstract_concept
establish a federal system	process
event	process
evolution	process
experiment	process
eye	entity
earth	entity
ebb and flow	process
echoes	property
education	process
electric current	property
electricity	force
end	process
enemy	entity
environment	entity
enzyme	substance
express	entity
eardrum	entity
early warning	process
earplugs	entity
earth plate	entity
earth's core	entity
earthquake	process
earthquake source	entity
earthquakes and volcanic eruptions	process
eating	process
ecology	abstract_concept
economy	abstract_concept
edited gene	entity
effective	property
efficient	property
egg	entity
eigenvalues	property
electric age	abstract_concept
electrical energy	property
electrical equipment	entity
electromagnetic antenna	entity
electromagnetic waves	property
electromagnetism	force
electron	entity
electron density	property
electron transfer	process
electronic component	entity
element properties	property
elizabeth bennet	entity
elizabeth bennett	entity
elliptical	property
embryo	entity
emotional basis	property
emotional expression	process
emperor meiji	entity
emptiness	property
emptying	process
encrypted data	substance
encryption	process
encryption algorithm	abstract_concept
ending	process
endocrine organs	entity
energy conversion	process
energy distribution	process
energy flow	process
energy level	property
energy size	property
engine	entity
engine sound	property
engineer	entity
enhancer	entity
enter	process
epidemic	process
equation	abstract_concept
equipment	entity
era	property
eradication	process
eraser	entity
erasing	process
ernest hemingway	entity
eruption	process
estimate	property
etiology	abstract_concept
evaluate	process
evening	property
evidence	abstract_concept
examination	process
exchange rate	property
exciter	entity
execution	process
exhaust gas	substance
exhaust pipe	entity
expected return	property
expenditure	property
expensive	property
experience	abstract_concept
explaining	process
eye socket	entity
eyelid	entity
""")

_load("""
food	substance
fuel	substance
failure	property
family	entity
father	entity
feudal autocracy	abstract_concept
feudal ruler self-help movement	process
field	entity
foundation	entity
four years	property
fruit	substance
funding	substance
factory	entity
fault	process
feudal rule	abstract_concept
filter	entity
finished product	substance
fire	process
follower	entity
forgetting	process
fracture	entity
framework	abstract_concept
frequency	property
function	abstract_concept
funds	substance
f scott fitzgerald	entity
facilities	entity
facts	abstract_concept
fail	process
faith	abstract_concept
falling stone	entity
false	property
family honor	abstract_concept
family member	entity
fan blade	entity
farmer	entity
fast	property
fate	abstract_concept
feature	property
features	property
federal parliament	entity
feeding	process
feet	entity
fence	entity
fertilizer	substance
feudal theocracy	abstract_concept
feudalism	abstract_concept
fighter	entity
fighting	process
figure	entity
file system	abstract_concept
filling	process
film	entity
finance	process
financial balance	abstract_concept
find	process
fire fighting methods	abstract_concept
firepower	property
fission	process
fist	entity
fitness	property
flavor	property
flaw	property
flour	substance
flow	process
flower	entity
flowing	process
flows	process
fluctuation	property
funds	substance
""")

_load = _load  # 保持引用便于测试

# G–M 段（从 TSV 读入，避免 shell 引号问题；内容与人工判定一致）
from pathlib import Path as _P

_tsv = _P(__file__).with_name("scar_type_data_gm.tsv")
if _tsv.is_file():
    _load(_tsv.read_text(encoding="utf-8"))

_tsv2 = _P(__file__).with_name("scar_type_data_rest.tsv")
if _tsv2.is_file():
    _load(_tsv2.read_text(encoding="utf-8"))

_load("""
aegean sea	entity
atom	entity
antigen	entity
architecture	abstract_concept
argument	abstract_concept
activation energy	property
actor	entity
air	substance
alexander empire	entity
algorithm	abstract_concept
america was born	process
athens culture	abstract_concept
atmosphere	entity
accelerator	entity
accuracy	property
achievement	property
adjust	process
aegean civilization	abstract_concept
america	entity
analyze	process
ancient india	entity
antibody	entity
arabian peninsula	entity
article	entity
athlete	entity
attack	process
attracts	process
audience	entity
average effect	property
ability	property
absorb	process
acceptance	process
accepting	process
account	entity
accounting	abstract_concept
acidic substance	substance
acoustic medium	substance
acquaintance	entity
acquisition	process
act	process
action	process
active element	entity
active site	entity
actors	entity
adapt to the environment	process
adaptation	process
address	property
adhesive	substance
adjust aperture and shutter speed	process
adjust parameters	process
adjuster	entity
administrator	entity
adsorbent	substance
advocating	process
affair	process
age	property
aid	substance
air circulation	process
airplane	entity
aldous huxley	entity
alexander ii	entity
alkaline substance	substance
allocate	process
alternate steps	abstract_concept
alveoli	entity
ambition	property
amino acid	substance
amnesia	property
amplitude	property
analysis object	entity
analysis process	process
analysis results	property
analytical method	abstract_concept
anchor	entity
anger	property
animal	entity
answer	abstract_concept
anti-confucianism	abstract_concept
anti-french coalition	entity
antigen tolerance	property
antivirus	entity
aperture	entity
apoptosis	process
appetite	property
applied magnetic field	force
architect	entity
area	property
arguing	process
armand	entity
arms	entity
army	entity
arrest	process
arriving	process
arthur conan doyle	entity
artificial	property
artificial neural networks	entity
ascent	process
asleep	property
assessment	process
astronaut	entity
atomic arrangement	abstract_concept
atomic interaction	process
atomic nucleus	entity
atomic number	property
atomic orbital	entity
atomic potential field	property
atonement	abstract_concept
attacks	process
attraction	force
attributes	property
avatar	entity
average behavior	property
average value	property
avoid	process
awake	property
axiom	abstract_concept
""")
