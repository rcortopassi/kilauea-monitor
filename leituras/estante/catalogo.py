"""Catalogo da estante: a ordem de leitura combinada (0 a 316) + leituras paralelas.

Formato de cada linha:  ordem | tipo | fase | cesg | paginas | titulo | autor
  tipo:  L = literatura/historia   P = ideias (filosofia, teologia, espiritualidade...)
  fase:  1..7 (ver FASES); 9 = leituras paralelas (fora do plano diario)
  cesg:  1 se faz parte das leituras do CESG
  paginas: ESTIMATIVA (o site deixa corrigir livro a livro)
"""

FASES = {
    1: "Fase 1 — Brasil",
    2: "Fase 2 — Portugal",
    3: "Fase 3 — Antiguidade",
    4: "Fase 4 — Idade Média",
    5: "Fase 5 — Renascimento e séc. XVII",
    6: "Fase 6 — Século XIX",
    7: "Fase 7 — Século XX e contemporâneos",
    9: "Leituras paralelas (diárias)",
}

# Divisao em partes (cantos, capitulos) que o plano diario respeita: o site
# nunca manda parar no meio de uma parte. Cada parte: (titulo, peso), onde o
# peso e o tamanho relativo. O usuario pode trocar por um sumario com paginas.
ROMANOS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII",
           "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX", "XXI", "XXII", "XXIII", "XXIV"]
# Odisseia: numero de versos de cada canto no grego (o tamanho na traducao e proporcional)
_VERSOS_ODISSEIA = [444, 434, 497, 847, 493, 331, 347, 586, 566, 574, 640, 453,
                    440, 533, 557, 481, 606, 428, 604, 394, 434, 501, 372, 548]
PARTES = {
    0: [(f"Canto {r}", v) for r, v in zip(ROMANOS, _VERSOS_ODISSEIA)],
}

# Sumarios com a pagina inicial de cada parte, transcritos das edicoes do
# usuario (o numero de paginas do livro, acima, e a ultima pagina de leitura,
# sem bibliografia e indices).
PARTES_PG = {
    # No Principio Deus Criou (DIEL) - indice nas pp. 153-157
    52: [
        ("Introdução e Cap. I — No princípio Deus criou os céus e a terra", 7),
        ("Cap. II — A leitura cristã da Criação", 21),
        ("Cap. III — O amor de Deus, razão primeira e última da Criação", 31),
        ("Cap. IV — A Criação e o conhecimento científico do mundo", 47),
        ("Cap. V — A Providência de Deus", 65),
        ("Cap. VI — O problema do mal na Criação", 83),
        ("Cap. VII — Os anjos, seres espirituais e criaturas criadas por Deus", 97),
        ("Cap. VIII — O homem, uno em corpo e alma, criado à imagem do Criador", 113),
        ("Cap. IX — Natural e sobrenatural", 129),
        ("Cap. X — O pecado original", 137),
    ],
    # O Jardim das Aflicoes (Vide, 3a ed.): por secoes (§), porque os capitulos
    # sao muito longos (o cap. 9 tem 104 paginas)
    166: [
        ("Notas do editor e do autor; Prefácio", 11),
        ("§1 Introdução — O que Epicuro veio fazer aqui, ou: Biografia deste livro", 25),
        ("§2 As conferências no MASP", 40),
        ("§3 Pessanha e o pensamento ocidental", 48),
        ("§4 Uma profissão-de-fé epicurista. A matéria segundo Epicuro", 55),
        ("§5 Um piedoso subterfúgio", 61),
        ("§6–7 A imaginação dos deuses; Epicuro crítico de Demócrito", 65),
        ("§8 O remédio de todos os males", 73),
        ("§9 A abolição da consciência", 76),
        ("§10 A fumaça e o fogo", 91),
        ("§11 O convite ao sono", 94),
        ("§12 A servidão voluntária", 100),
        ("§13 Dos cães de Pavlov ao lava-rápido cerebral", 105),
        ("§14 Porcarias epicúreas", 119),
        ("§15 A fuga para o jardim", 129),
        ("§16 Epicuro e Marx", 137),
        ("§17 Comentários à 11ª “Tese sobre Feuerbach”", 141),
        ("§18 A tradição materialista", 153),
        ("§19 A divinização do espaço (I): Pobres bantos", 169),
        ("§20 A divinização do espaço (II): O infinito de Nicolau de Cusa", 176),
        ("§21 A divinização do tempo (I): A força dos meios", 201),
        ("§22 A divinização do tempo (II): Beaux draps", 223),
        ("§23 Revisão do itinerário percorrido", 235),
        ("§24 O véu do templo", 239),
        ("§25 Leviatã e Beemot", 250),
        ("§26 De Hegel a Comte", 261),
        ("§27 Translatio imperii. Breve história da idéia imperial", 266),
        ("§28 O Império contra-ataca", 297),
        ("§29 Aristocracia e sacerdócio no Império americano (I)", 303),
        ("§30 Aristocracia e sacerdócio no Império americano (II)", 324),
        ("§31 De Wilhelm Meister a Raskolnikov", 333),
        ("§32 As novas Tábuas da Lei, ou: O Estado bedel", 345),
        ("§33 Retorno ao MASP e ingresso no Jardim das Aflições", 365),
        ("Post-scriptum — Lápide: de te fabula narratur", 405),
        ("Posfácio: O que mudou no mundo duas décadas depois?", 411),
    ],
}

# livros que ja estao sendo lidos quando o site e criado (ordem -> peso)
LENDO_INICIAL = {0: 2, 56: 1, 166: 1}

_DADOS = """
0|L|3|0|576|Odisseia|Homero
1|L|1|0|300|Anchieta, o Apóstolo do Brasil|Joaquim Tomás
2|P|1|0|432|Como Ler Livros|Adler & Van Doren
3|L|1|0|400|Sermões|Pe. Antônio Vieira
4|P|1|0|240|A Vida Intelectual|Sertillanges
5|L|1|0|1100|Ficção Completa I|José de Alencar
6|P|1|0|200|O Trabalho Intelectual|Jean Guitton
7|L|1|0|1100|Ficção Completa II|José de Alencar
8|P|1|0|300|A Educação da Vontade|Jules Payot
9|L|1|0|1100|Ficção Completa III|José de Alencar
10|P|1|0|176|A Arte de Escrever|Schopenhauer
11|L|1|0|200|Contos de Machado de Assis (vol. 3)|Machado de Assis
12|P|1|0|300|Youcat|—
13|L|1|0|250|Casa de Pensão|Aluísio Azevedo
14|P|1|0|280|Cristianismo Puro e Simples|C.S. Lewis
15|L|1|0|730|Casa-Grande & Senzala|Gilberto Freyre
16|P|1|1|200|Introdução Geral à Teologia|—
17|L|1|0|500|Isaías Caminha / Policarpo Quaresma / Gonzaga de Sá|Lima Barreto
18|P|1|1|250|Conhecer a Bíblia|J. Monforte
19|L|1|0|200|Os Bruzundangas|Lima Barreto
20|P|1|0|200|Passagens Intrigantes da Bíblia|—
21|L|1|0|230|A Alma Encantadora das Ruas|João do Rio
22|P|1|1|250|Teologia Fundamental|J. Burggraf
23|L|1|0|180|Bandeira de Bolso|Manuel Bandeira
24|P|1|1|250|Manual Esquemático de Filosofia|I. Martins
25|L|1|0|1000|Ficção Completa I|José Lins do Rego
26|P|1|0|400|Platão I|Platão
27|L|1|0|1000|Ficção Completa II|José Lins do Rego
28|P|1|0|420|A República|Platão
29|L|1|0|220|S. Bernardo|Graciliano Ramos
30|P|1|0|320|Política|Aristóteles
31|L|1|0|290|Angústia|Graciliano Ramos
32|P|1|0|240|Aristóteles em Nova Perspectiva|Olavo de Carvalho
33|L|1|0|180|Vidas Secas|Graciliano Ramos
34|P|1|1|300|Manual Esquemático de História da Filosofia|I. Martins
35|L|1|0|400|Antologia Poética|Carlos Drummond de Andrade
36|P|1|0|200|Cícero|Cícero
37|L|1|0|1000|Obra Poética|Cecília Meireles
38|P|1|1|280|Gnoseologia|A. Llano
39|L|1|0|1200|Poesia Completa e Prosa|Vinicius de Moraes
40|P|1|1|280|Gnosiologia Realista|A. Llano
41|L|1|0|200|O Simples Coronel Madureira|Marques Rebelo
42|P|1|1|280|Metafísica|T. Alvira
43|L|1|0|300|O Homem que Calculava|Malba Tahan
44|P|1|1|300|Metafísica da Realidade|T. Melendo
45|L|1|0|160|Felicidade Clandestina|Clarice Lispector
46|P|1|1|380|Filosofía del Hombre|J. Arregui
47|L|1|0|200|Brasileiros Heróis da Fé|Altenfelder Silva
48|P|1|1|200|Antropologia Breve|J. Burgos
49|L|1|0|230|Tempo de Arraes|Antonio Callado
50|P|1|1|350|Fundamentos de Antropologia|R. Stork
51|L|1|0|200|A Velha Classe|Márcio Moreira Alves
52|P|1|1|150|No Princípio Deus Criou|P. Meneses
53|L|1|0|650|Os Cem Melhores Contos Brasileiros do Século|—
54|P|1|1|300|El Misterio de la Creación|J. Morales
55|L|1|0|200|Uma Cultura Ameaçada|Gilberto Freyre
56|P|1|1|250|Deus Uno e Trino|G. Lobo Méndez
57|L|1|0|250|Feliz Ano Velho|Marcelo Rubens Paiva
58|P|1|1|250|Dios Trino en Personas|J. Ibáñez
59|L|1|0|220|Suíte Tóquio|Giovana Madalosso
60|P|1|0|900|Jesus de Nazaré|Bento XVI
61|L|1|0|120|Poemas: Só Ser|Flávia Beckel
62|P|1|1|250|Jesus Cristo, Nosso Salvador|V. Barriendos
63|L|2|0|800|História de Portugal|João Ameal
64|P|2|1|250|Mãe de Deus e Mãe Nossa|A. Orozco
65|L|2|0|120|A Vingança de Agamémnon|Henrique Aires Vitória
66|P|2|1|220|A Vida da Graça|J.F. Pozo
67|L|2|0|150|Castro|António Ferreira
68|P|2|1|350|Teologia Moral Fundamental|R. Haro
69|L|2|0|500|Os Lusíadas|Camões
70|P|2|1|400|Moral Fundamental|A. Fernández
71|L|2|0|200|Sonetos|Bocage
72|P|2|1|450|Moral Especial|A. Fernández
73|L|2|0|900|Obras em Prosa|Fernando Pessoa
74|P|2|1|250|Cristãos na Sociedade|D. Melé
75|L|3|0|900|História da Literatura Ocidental I|Otto Maria Carpeaux
76|P|3|1|250|A Igreja|J.R. P. Arangüena
77|L|3|0|400|Mitologia|Thomas Bulfinch
78|P|3|1|200|O Direito da Igreja|D. Le Tourneau
79|L|3|0|150|Meu Livro de Fábulas|—
80|P|3|1|250|Os Sete Sacramentos|E. Moliné
81|L|3|0|700|Ilíada|Homero
82|P|3|1|400|El Misterio Eucarístico|J. Sayés
83|L|3|0|300|Oréstia|Ésquilo
84|P|3|1|250|Liturgia|J. Gutierrez
85|L|3|0|650|História da Educação na Antiguidade|Henri-Irénée Marrou
86|P|3|1|600|Historia de la Liturgia|M. Righetti
87|L|3|0|900|Obras Completas|Virgílio
88|P|3|1|250|Matrimônio e Família|J. Bañares
89|L|3|1|200|Breve História do Cristianismo|J. Orlandis
90|P|3|1|700|Teologia do Corpo|São João Paulo II
91|L|3|0|200|A Vida da Virgem|São Máximo, o Confessor
92|P|3|1|200|O Além|J. Sánchez de Alva
93|L|3|0|400|Vida e Glórias de São José|Edward Healy Thompson
94|P|3|1|250|Escatología|J. Alviar
95|L|3|0|300|São Paulo, o Apóstolo dos Gentios|A. Tricot
96|P|3|1|500|Historia de la Teología|J. Illanes
97|L|3|0|400|Vida dos Mártires|Alban Butler
98|P|3|0|190|O Problema da Dor|C.S. Lewis
99|L|3|1|300|Arqueologia Cristiana|J. Álvares
100|P|3|0|420|Deus no Banco dos Réus|C.S. Lewis
101|L|3|1|300|Arqueologia Cristiana|J. Herrero
102|P|3|0|160|A Arte da Guerra|Sun Tzu
103|L|3|0|250|História da Educação na Antiguidade Cristã|Ruy Afonso da Costa Nunes
104|P|3|0|250|O Peso da Glória|C.S. Lewis
105|L|3|0|150|Vida de Santo Antão|Santo Atanásio
106|P|3|0|250|Didascalicon|Hugo de São Vítor
107|L|4|0|500|Mil Histórias sem Fim, vol. 1|—
108|P|4|0|350|Escada do Paraíso|São João Clímaco
109|L|4|0|1000|Legenda Áurea|Tiago de Voragine
110|P|4|0|250|Institutiones|Cassiodoro
111|L|4|0|500|A Inveja dos Anjos|C. Stephen Jaeger
112|P|4|0|200|Os Quatro Amores|C.S. Lewis
113|L|4|0|200|Carlos Magno e a Restauração da Educação|James Bass Mullinger
114|P|4|0|150|A Agonia de Cristo|São Thomas More
115|L|4|0|300|História da Educação na Idade Média|Ruy Afonso da Costa Nunes
116|P|4|0|180|O Príncipe|Maquiavel
117|L|4|0|300|Heróis e Maravilhas da Idade Média|Jacques Le Goff
118|P|4|0|150|Maquiavel ou a Confusão Demoníaca|Olavo de Carvalho
119|L|4|0|250|Santa Hildegarda de Bingen|Régine Pernoud
120|P|4|0|400|Livro da Vida|Santa Teresa de Ávila
121|L|4|0|300|A Vida de São Bernardo|Robert Thomas
122|P|4|0|220|Caminho de Perfeição|Santa Teresa de Ávila
123|L|4|0|400|Três Monges Rebeldes|M. Raymond
124|P|4|0|250|As Moradas do Castelo Interior|Santa Teresa de Ávila
125|L|4|0|300|A Glória das Cruzadas|Steve Weidenkopf
126|P|4|0|400|Subida do Monte Carmelo|São João da Cruz
127|L|4|0|300|Vida de São Francisco|Tomás de Celano
128|P|4|0|150|Dez Razões|Santo Edmundo Campion
129|L|4|0|300|Vida e Milagres de Santa Clara|—
130|P|4|0|180|Visões de Descartes|Olavo de Carvalho
131|L|4|0|250|História de Santo Antônio de Pádua|—
132|P|4|0|700|O Espírito das Leis|Montesquieu
133|L|4|0|250|Vida de São Domingos|Lacordaire
134|P|4|0|400|Reflexões sobre a Revolução na França|Edmund Burke
135|L|4|0|200|Santo Tomás de Aquino|G.K. Chesterton
136|P|4|0|250|Prática do Amor a Jesus Cristo|Santo Afonso
137|L|4|0|400|Catarina de Siena|Sigrid Undset
138|P|4|0|250|A Paixão de N. S. Jesus Cristo|Santo Afonso
139|L|4|0|600|A Morte de Arthur I|Thomas Malory
140|P|4|0|600|Glórias de Maria|Santo Afonso
141|L|4|0|600|A Morte de Arthur II|Thomas Malory
142|P|4|0|250|Tratado da Verdadeira Devoção|São Luís de Montfort
143|L|4|0|250|A Vida de Santa Rita de Cássia|—
144|P|4|0|200|O Segredo Admirável do Santíssimo Rosário|São Luís de Montfort
145|L|5|0|300|História da Educação no Renascimento|Ruy Afonso da Costa Nunes
146|P|5|0|200|Saltério da Virgem|São Boaventura
147|L|5|0|1200|Dom Quixote|Cervantes
148|P|5|0|400|Vida e Paixão do Cordeiro de Deus|Ana Catarina Emmerich
149|L|5|0|1260|Obra Completa|William Shakespeare
150|P|5|0|300|História de uma Alma|Santa Teresinha
151|L|5|0|300|História da Educação no Século XVII|Ruy Afonso da Costa Nunes
152|P|5|0|700|Diário de Santa Faustina|Santa Faustina
153|L|5|0|300|O Método Pedagógico dos Jesuítas|Leonel Franca
154|P|5|0|250|Tremendas Trivialidades|G.K. Chesterton
155|L|6|0|900|História da Literatura Ocidental II|Otto Maria Carpeaux
156|P|6|0|120|A Abolição do Homem|C.S. Lewis
157|L|6|0|600|Fausto|Goethe
158|P|6|0|250|Sobre Histórias|C.S. Lewis
159|L|6|0|420|Orgulho e Preconceito|Jane Austen
160|P|6|0|200|A Última Noite do Mundo|C.S. Lewis
161|L|6|0|300|Persuasão|Jane Austen
162|P|6|0|110|A Anatomia de um Luto|C.S. Lewis
163|L|6|0|500|Emma|Jane Austen
164|P|6|0|300|Como Ser um Conservador|Roger Scruton
165|L|6|0|300|Frankenstein|Mary Shelley
166|P|6|0|426|O Jardim das Aflições|Olavo de Carvalho
167|L|6|0|400|Selected Tales|Edgar Allan Poe
168|P|6|0|450|O Imbecil Coletivo|Olavo de Carvalho
169|L|6|0|300|O Pai Goriot|Balzac
170|P|6|0|600|A Longa Marcha da Vaca para o Brejo (I)|Olavo de Carvalho
171|L|6|0|450|O Visconde de Bragelonne|Alexandre Dumas
172|P|6|0|550|O Imbecil Juvenil (II)|Olavo de Carvalho
173|L|6|0|380|O Morro dos Ventos Uivantes|Emily Brontë
174|P|6|0|550|O Leão e os Ossos (III)|Olavo de Carvalho
175|L|6|0|550|Jane Eyre|Charlotte Brontë
176|P|6|0|200|A Nova Era e a Revolução Cultural|Olavo de Carvalho
177|L|6|0|500|Oliver Twist|Charles Dickens
178|P|6|0|150|O Futuro do Pensamento Brasileiro|Olavo de Carvalho
179|L|6|0|300|Contos|Charles Dickens
180|P|6|0|250|A Filosofia e seu Inverso|Olavo de Carvalho
181|L|6|0|500|Um Conto de Duas Cidades|Charles Dickens
182|P|6|0|250|A Dialética Simbólica|Olavo de Carvalho
183|L|6|0|650|Moby Dick|Herman Melville
184|P|6|0|250|A Consciência de Imortalidade|Olavo de Carvalho
185|L|6|0|450|Os Trabalhadores do Mar|Victor Hugo
186|P|6|0|200|A Formação do Imaginário|—
187|L|6|0|400|Madame Bovary|Gustave Flaubert
188|P|6|0|250|Os EUA e a Nova Ordem Mundial|Dugin & Olavo de Carvalho
189|L|6|0|150|Três Contos|Gustave Flaubert
190|P|6|0|250|Louis Lavelle|Olavo de Carvalho
191|L|6|0|400|O Santo Cura d'Ars|Francis Trochu
192|P|6|0|250|Mário Ferreira dos Santos|Olavo de Carvalho
193|L|6|0|550|A Canção de Bernadette|Franz Werfel
194|P|6|0|300|Conhecimento por Presença|Ronald Robson
195|L|6|0|400|História de uma Família|Stéphane-Joseph Piat
196|P|6|0|250|Contra a Vida Intelectual|Ronald Robson
197|L|6|0|200|Luís e Zélia Martin|Hélène Mongin
198|P|6|0|250|A Morte da Cultura Cristã|John Senior
199|L|6|0|850|Anna Kariênina|Lev Tolstói
200|P|6|0|250|A Restauração da Cultura Cristã|John Senior
201|L|6|0|130|Duas Narrativas Fantásticas|Fiódor Dostoiévski
202|P|6|0|250|A Descoberta do Outro|Gustavo Corção
203|L|6|0|600|Nova Antologia do Conto Russo|—
204|P|6|0|350|A Corrupção da Inteligência|Flávio Gordon
205|L|6|0|120|O Médico e o Monstro|R.L. Stevenson
206|P|6|0|400|Por Trás da Máscara|Flavio Morgenstern
207|L|6|0|500|Drácula|Bram Stoker
208|P|6|0|300|Por que o Brasil é um País Atrasado?|Luiz Philippe de Orleans e Bragança
209|L|6|0|400|Dom Bosco|—
210|P|6|0|180|O Esplendor da Verdade|São João Paulo II
211|L|6|0|400|O Fabuloso Livro Azul|Andrew Lang
212|P|6|0|220|Luz do Mundo|Bento XVI
213|L|6|0|400|O Fabuloso Livro Vermelho|Andrew Lang
214|P|6|0|300|Joseph Ratzinger (volume azul)|Joseph Ratzinger
215|L|6|0|400|O Fabuloso Livro Verde|Andrew Lang
216|P|6|0|300|Documento de Aparecida|CELAM
217|L|6|0|400|O Fabuloso Livro Amarelo|Andrew Lang
218|P|6|0|220|Evangelii Gaudium|Papa Francisco
219|L|6|0|350|Vidas de Homens Notáveis|Henry Thomas
220|P|6|0|100|Gaudete et Exsultate|Papa Francisco
221|L|7|0|900|História da Literatura Ocidental III|Otto Maria Carpeaux
222|P|7|0|150|Christus Vivit|Papa Francisco
223|L|7|0|500|A Sagração da Primavera|Modris Eksteins
224|P|7|0|150|Deus é Jovem|Papa Francisco
225|L|7|0|250|Nossa Senhora de Fátima|—
226|P|7|0|350|Amor e Responsabilidade|Karol Wojtyła
227|L|7|0|250|A Inocência do Padre Brown|G.K. Chesterton
228|P|7|0|300|Cartas I|São Josemaría Escrivá
229|L|7|0|250|A Sabedoria do Padre Brown|G.K. Chesterton
230|P|7|0|300|Cartas II|São Josemaría Escrivá
231|L|7|0|250|A Incredulidade do Padre Brown|G.K. Chesterton
232|P|7|0|300|Em Diálogo com o Senhor|São Josemaría Escrivá
233|L|7|0|250|O Segredo do Padre Brown|G.K. Chesterton
234|P|7|0|250|Sobre Deus, a Igreja e o Mundo|Fernando Ocáriz
235|L|7|0|250|O Escândalo do Padre Brown|G.K. Chesterton
236|P|7|0|300|Sonhai e Ficareis Aquém|Pedro Casciaro
237|L|7|0|160|A Porta Estreita|André Gide
238|P|7|0|300|A Virgem Nossa Senhora|Federico Suárez
239|L|7|0|250|O Nó de Víboras|François Mauriac
240|P|7|0|250|Conhece-te a Ti Mesmo|José Maria Rodríguez Ramos
241|L|7|0|300|Diário de um Pároco de Aldeia|Georges Bernanos
242|P|7|0|150|A Paz Interior|Jacques Philippe
243|L|7|0|200|O Grande Gatsby|F. Scott Fitzgerald
244|P|7|0|200|A Conquista das Virtudes|Francisco Faus
245|L|7|0|1000|Obra Escolhida I|Somerset Maugham
246|P|7|0|200|Às Fontes da Alegria|Cônego F. Vidal
247|L|7|0|1000|Obra Escolhida II|Somerset Maugham
248|P|7|0|200|O Poder Oculto da Amabilidade|Lawrence Lovasik
249|L|7|0|300|São Maximiliano Kolbe|—
250|P|7|0|150|Decenário do Espírito Santo|Francisca Javiera del Valle
251|L|7|0|250|Padre Pio|Elena Bergadano
252|P|7|0|300|A Direção da Alma e a Vida Perfeita|—
253|L|7|0|330|O Hobbit|J.R.R. Tolkien
254|P|7|0|150|Em Busca do Equilíbrio|Maurício Domínguez Pérez
255|L|7|0|576|O Senhor dos Anéis 1 — A Sociedade do Anel|J.R.R. Tolkien
256|P|7|0|150|Anselm Grün|Anselm Grün
257|L|7|0|464|O Senhor dos Anéis 2 — As Duas Torres|J.R.R. Tolkien
258|P|7|0|200|Pescadores de Homens|Fábio Henrique Carvalheiro
259|L|7|0|504|O Senhor dos Anéis 3 — O Retorno do Rei|J.R.R. Tolkien
260|P|7|0|250|Minhas Irmãs, as Santas|Colleen Carroll Campbell
261|L|7|0|450|O Silmarillion|J.R.R. Tolkien
262|P|7|0|150|O Privilégio de Ser Mulher|Alice von Hildebrand
263|L|7|0|300|Os Filhos de Húrin|J.R.R. Tolkien
264|P|7|0|200|Amor e Casamento|Cormac Burke
265|L|7|0|300|Beren e Lúthien|J.R.R. Tolkien
266|P|7|0|200|Noivado & Casamento|Rafael Llano Cifuentes
267|L|7|0|300|A Queda de Gondolin|J.R.R. Tolkien
268|P|7|0|200|As Crises Conjugais|Rafael Llano Cifuentes
269|L|7|0|600|Contos Inacabados|J.R.R. Tolkien
270|P|7|0|200|Grande este Mistério|Andrea & Fábio Toledo
271|L|7|0|200|The Magician's Nephew|C.S. Lewis
272|P|7|0|200|Dois em Deus (?)|Javier Vidal-Quadras
273|L|7|0|200|The Lion, the Witch and the Wardrobe|C.S. Lewis
274|P|7|0|200|O Casamento e a Vida em Família|—
275|L|7|0|220|The Horse and His Boy|C.S. Lewis
276|P|7|0|300|A Arte de Ensinar|Gilbert Highet
277|L|7|0|230|Prince Caspian|C.S. Lewis
278|P|7|0|300|Ensine do seu Jeito|John Holt & Patrick Farenga
279|L|7|0|250|The Voyage of the Dawn Treader|C.S. Lewis
280|P|7|0|200|For the Children's Sake|Susan Schaeffer Macaulay
281|L|7|0|250|The Silver Chair|C.S. Lewis
282|P|7|0|200|Educar na Curiosidade|Catherine L'Ecuyer
283|L|7|0|210|The Last Battle|C.S. Lewis
284|P|7|0|150|Os 4 Temperamentos|Italo Marsili
285|L|7|0|350|Até que Tenhamos Rostos|C.S. Lewis
286|P|7|0|150|Sexualidade Infantil|Samia Marsili
287|L|7|0|150|O Grande Divórcio|C.S. Lewis
288|P|7|0|200|Felicidade, Personalidade e Vocação|Pedro Menezes
289|L|7|0|150|A Revolução dos Bichos|George Orwell
290|P|7|0|450|12 Regras para a Vida|Jordan Peterson
291|L|7|0|180|Ficções|Jorge Luis Borges
292|P|7|0|130|Sociedade do Cansaço|Byung-Chul Han
293|L|7|0|600|A Revolta de Atlas I|Ayn Rand
294|P|7|0|90|Ideias para Adiar o Fim do Mundo|Ailton Krenak
295|L|7|0|450|A Revolta de Atlas II|Ayn Rand
296|P|7|0|250|Escape into Meaning|Evan Puschak
297|L|7|0|650|A Revolta de Atlas III|Ayn Rand
298|P|7|0|270|As Coisas que Você Só Vê Quando Desacelera|Haemin Sunim
299|L|7|0|250|2001: Uma Odisseia no Espaço|Arthur C. Clarke
300|P|7|0|300|Where Angels Walk|Joan Wester Anderson
301|L|7|0|300|Maus|Art Spiegelman
302|P|7|0|450|Os 7 Hábitos das Pessoas Altamente Eficazes|Stephen R. Covey
303|L|7|0|400|Opus Dei|John L. Allen Jr.
304|P|7|0|350|A Arte da Negociação|Donald Trump
305|L|7|0|450|O Último Reino|Bernard Cornwell
306|L|7|0|250|Momo|Michael Ende
307|L|7|0|300|De Amor y de Sombra|Isabel Allende
308|L|7|0|200|Le Grand Môme|A.D.G.
309|L|7|0|220|Au Maléfice du Doute|John Wainwright
310|L|7|0|180|Vá Aonde Seu Coração Mandar|Susanna Tamaro
311|L|7|0|400|Coisas que Ninguém Sabe|Alessandro D'Avenia
312|L|7|0|220|The Notebook|Nicholas Sparks
313|L|7|0|350|Tudo o que Eu Sei sobre o Amor|Dolly Alderton
314|L|7|0|400|These Few Precious Days|Christopher Andersen
315|L|7|0|300|Em Busca de Mim|Viola Davis
316|L|7|0|850|O Livro das Virtudes|William J. Bennett
1001|P|9|0|2200|Bíblia de Jerusalém|—
1002|P|9|0|1500|Bíblia Sagrada — Pastoral Catequética|—
1003|P|9|0|500|Falar com Deus 1 — Advento, Natal, Epifania|Francisco Fernández-Carvajal
1004|P|9|0|500|Falar com Deus 2 — Quaresma, Semana Santa, Páscoa|Francisco Fernández-Carvajal
1005|P|9|0|500|Falar com Deus 3 — Tempo Comum (1)|Francisco Fernández-Carvajal
1006|P|9|0|500|Falar com Deus 4 — Tempo Comum (2)|Francisco Fernández-Carvajal
1007|P|9|0|500|Falar com Deus 5 — Tempo Comum (3)|Francisco Fernández-Carvajal
1008|P|9|0|500|Falar com Deus 6 — Festas litúrgicas e Santos (1)|Francisco Fernández-Carvajal
1009|P|9|0|500|Falar com Deus 7 — Festas litúrgicas e Santos (2)|Francisco Fernández-Carvajal
1010|P|9|0|800|Vidas dos Santos para Todos os Dias do Ano|Alban Butler
1011|P|9|0|250|Imitação de Cristo|Tomás de Kempis
1012|P|9|0|200|Meditações para o Advento e o Natal|Santo Tomás de Aquino
1013|P|9|0|200|Meditando com Santa Faustina|—
1014|P|9|0|400|Gramática Latina|Pe. João Ravizza
"""


def carregar():
    """Lista de dicts, um por livro, na ordem de leitura."""
    livros = []
    for linha in _DADOS.strip().splitlines():
        ordem, tipo, fase, cesg, pags, titulo, autor = linha.split("|")
        livros.append({
            "id": int(ordem),
            "tipo": tipo,
            "fase": int(fase),
            "cesg": cesg == "1",
            "paginas": int(pags),
            "titulo": titulo,
            "autor": "" if autor == "—" else autor,
            "paralela": int(fase) == 9,
        })
    return livros
