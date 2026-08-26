/* A reforma tributária nos dois escritórios — motor e montagem da página.
   Ponto de partida: os dois escritórios no Simples Nacional (Anexo IV).
   A partir de 2027 cada um escolhe o caminho: seguir no Simples normal,
   passar ao Simples híbrido (IBS/CBS por fora, com crédito) ou — no caso
   de SP — sair para o regime regular com crédito. */
(function () {
  "use strict";
  const C = window.Calc, F = C.Fmt;

  const SPEC = [
    { g: "Escritório de São Paulo",
      antes: '<div class="campo"><div class="campo-linha" style="margin-bottom:7px"><label>A partir de 2027, SP fica em</label></div>' +
        '<div class="seletor" role="group" aria-label="Caminho de SP na reforma">' +
        '<button type="button" data-sel="spModo" data-val="REG" aria-pressed="true">Regime com crédito</button>' +
        '<button type="button" data-sel="spModo" data-val="HIB" aria-pressed="false">Simples híbrido</button>' +
        '<button type="button" data-sel="spModo" data-val="NORMAL" aria-pressed="false">Simples normal</button></div>' +
        '<div class="ajuda">Regime com crédito: sai do Simples, paga IBS/CBS da advocacia por fora com créditos, mais IRPJ/CSLL do Presumido e o ISS enquanto durar. Híbrido: continua no Simples, mas recolhe IBS/CBS por fora, com crédito integral ao cliente. Normal: tudo no DAS, sem destacar crédito.</div></div>',
      campos: [
      { m: 1, k: "fatSP", r: "Faturamento", un: "R$/mês", min: 10000, max: 400000, passo: 5000, v: 100000 },
      { m: 1, k: "rbt12SP", r: "Receita dos últimos 12 meses", un: "R$", min: 0, max: 4800000, passo: 10000, v: 1200000,
        aj: "O RBT12 de SP, que define a faixa do Anexo IV enquanto o escritório estiver no Simples. O padrão equivale a 12 × R$ 100 mil." },
      { m: 1, k: "custos", r: "Custos que geram crédito", un: "R$/mês", min: 0, max: 500000, passo: 500, v: 15000,
        aj: "Aluguel, energia, software, contabilidade — despesas com nota de fornecedor no regime regular. Folha e pró-labore não geram crédito. Só valem fora do Simples normal." },
      { k: "irpj", r: "IRPJ e CSLL no Presumido", un: "%", min: 0, max: 20, passo: 0.01, v: 7.68,
        aj: "Devidos se SP sair do Simples: presunção de 32% × (15% + 9%). O adicional de 10% do IRPJ, se houver, entra aqui." }
    ]},
    { g: "ISS de SP fora do Simples",
      antes: '<div class="campo"><div class="seletor" role="group" aria-label="Forma de cobrança do ISS">' +
        '<button type="button" data-sel="issModo" data-val="PCT" aria-pressed="true">% da receita</button>' +
        '<button type="button" data-sel="issModo" data-val="SUP" aria-pressed="false">Fixo · uniprofissional</button></div>' +
        '<div class="ajuda">Vale apenas se SP sair do Simples: de 2027 a 2032 o escritório paga o ISS que restar do cronograma. A sociedade uniprofissional recolhe ISS fixo por advogado — e perde esse regime junto com o ISS, porque o IBS/CBS não têm equivalente.</div></div>',
      campos: [
      { k: "iss", r: "Alíquota sobre a receita", un: "%", min: 0, max: 5, passo: 0.25, v: 5,
        aj: "5% na capital paulista." },
      { m: 1, k: "issFixo", r: "ISS fixo da sociedade", un: "R$/mês", min: 0, max: 100000, passo: 100, v: 2000,
        aj: "Some o ISS fixo de todos os advogados e divida por três, se o carnê for trimestral — na capital paulista é por profissional, por trimestre." }
    ]},
    { g: "Escritório de Brasília",
      antes: '<div class="campo"><div class="campo-linha" style="margin-bottom:7px"><label>A partir de 2027, Brasília fica em</label></div>' +
        '<div class="seletor" role="group" aria-label="Caminho de Brasília na reforma">' +
        '<button type="button" data-sel="bsbModo" data-val="NORMAL" aria-pressed="true">Simples normal</button>' +
        '<button type="button" data-sel="bsbModo" data-val="HIB" aria-pressed="false">Simples híbrido</button></div>' +
        '<div class="ajuda">Normal: tudo no DAS, sem destacar crédito. Híbrido: continua no Simples, mas recolhe IBS/CBS por fora com crédito integral ao cliente — só tende a valer a pena com carteira dominada por clientes PJ que exijam o crédito.</div></div>',
      campos: [
      { m: 1, k: "fatBSB", r: "Faturamento", un: "R$/mês", min: 1000, max: 400000, passo: 1000, v: 30000,
        aj: "Entre R$ 20 e 40 mil por mês, pela faixa citada." },
      { m: 1, k: "rbt12BSB", r: "Receita dos últimos 12 meses", un: "R$", min: 0, max: 4800000, passo: 10000, v: 360000,
        aj: "O RBT12 de Brasília. O padrão equivale a 12 × R$ 30 mil." },
      { m: 1, k: "custosBSB", r: "Custos que geram crédito", un: "R$/mês", min: 0, max: 200000, passo: 500, v: 3000,
        aj: "Usados apenas no Simples híbrido, para abater o IBS/CBS recolhido por fora." }
    ]},
    { g: "Premissas da reforma", campos: [
      { k: "cbsRef", r: "CBS de referência", un: "%", min: 5, max: 15, passo: 0.1, v: 8.8 },
      { k: "ibsRef", r: "IBS de referência", un: "%", min: 10, max: 22, passo: 0.1, v: 17.7,
        aj: "A estimativa oficial soma 26,5%; projeções de mercado chegam a 28%. A alíquota final sai por resolução do Senado." },
      { k: "red", r: "Redução para advocacia", un: "%", min: 0, max: 60, passo: 5, v: 30,
        aj: "Profissões intelectuais regulamentadas — art. 127 da LC 214/2025." }
    ]}
  ];

  const PADRAO = {};
  SPEC.forEach(g => g.campos.forEach(c => { PADRAO[c.k] = c.v; }));
  PADRAO.spModo = "REG";
  PADRAO.bsbModo = "NORMAL";
  PADRAO.issModo = "PCT";
  const P = Object.assign({}, PADRAO);

  const ANOS = [2026, 2027, 2028, 2029, 2030, 2031, 2032, 2033];
  const MODO = { REG: "regime com crédito", HIB: "Simples híbrido", NORMAL: "Simples normal" };

  /* ============================ motor ============================ */
  /* Alíquotas-padrão vigentes em cada ano, conforme EC 132/2023 e
     LC 214/2025 (cronograma dos arts. 343 a 347):
     2026        CBS 0,9% + IBS 0,1%, compensáveis com PIS/COFINS —
                 carga prática igual à de hoje (teste);
     2027–2028   CBS cheia menos 0,1 p.p., IBS de 0,1% (0,05% estadual
                 + 0,05% municipal), ISS integral, fim de PIS/COFINS;
     2029–2032   IBS a 10/20/30/40% da referência enquanto o ISS cai
                 para 90/80/70/60% do atual (a alíquota exata do IBS
                 sairá por resolução do Senado; aqui, proporcional);
     2033        referência plena, ISS extinto. */
  function aliquotas(p, ano) {
    if (ano <= 2026) return { cbs: 0.9, ibs: 0.1, iss: 1, pisCof: 1, teste: true };
    if (ano <= 2028) return { cbs: Math.max(0, p.cbsRef - 0.1), ibs: 0.1, iss: 1, pisCof: 0 };
    if (ano <= 2032) {
      const n = ano - 2028; /* 1..4 */
      return { cbs: p.cbsRef, ibs: p.ibsRef * 0.1 * n, iss: 1 - 0.1 * n, pisCof: 0 };
    }
    return { cbs: p.cbsRef, ibs: p.ibsRef, iss: 0, pisCof: 0 };
  }

  /* Anexo IV do Simples Nacional (advocacia): teto, alíquota nominal,
     parcela a deduzir. */
  const ANEXO4 = [
    [180000, 0.045, 0],
    [360000, 0.09, 8100],
    [720000, 0.102, 12420],
    [1800000, 0.14, 39780],
    [3600000, 0.22, 183780],
    [4800000, 0.33, 828000]
  ];
  function simples(rbt12) {
    const base = Math.max(1, rbt12);
    for (let i = 0; i < ANEXO4.length; i++) {
      if (base <= ANEXO4[i][0]) {
        return { aliq: Math.max(0, (base * ANEXO4[i][1] - ANEXO4[i][2]) / base),
          faixa: i + 1, nominal: ANEXO4[i][1] };
      }
    }
    return null; /* acima do teto de R$ 4,8 mi */
  }

  /* Partilha aproximada do DAS no Anexo IV: 38% IRPJ/CSLL, 22% PIS/COFINS,
     40% ISS. No híbrido, a fatia de tributos sobre o consumo sai do DAS e
     vira IBS/CBS por fora; a de IRPJ/CSLL fica, junto com o ISS que restar. */
  const SH_IRPJ = 0.38, SH_PISCOF = 0.22, SH_ISS = 0.40;

  /* IBS/CBS da advocacia recolhido por fora num ano, embutido no preço
     atual (t/(1+t)), com crédito sobre os custos. */
  function ivaForaAno(p, fat, custos, ano, sobre) {
    const a = aliquotas(p, ano);
    const fator = sobre && sobre.aliqTotal != null ? sobre.aliqTotal / (p.cbsRef + p.ibsRef) : 1;
    const vig = (a.teste ? 0 : a.cbs + a.ibs) * fator / 100;
    const tAdv = vig * (1 - p.red / 100);
    const debito = fat * tAdv / (1 + tAdv);
    const credito = Math.min(debito, custos * vig / (1 + vig));
    return { aliq: a, vig: vig, tAdv: tAdv, debito: debito,
      credito: credito, iva: Math.max(0, debito - credito) };
  }

  const issForaSP = p => (p.issModo === "SUP" ? p.issFixo : p.fatSP * p.iss / 100);

  /* Carga mensal de um escritório num ano, conforme o caminho escolhido.
     Até 2026 todos seguem no Simples de hoje (o teste é compensável). */
  function cargaEscritorio(p, qual, ano, sobre) {
    const fat = qual === "SP" ? p.fatSP : p.fatBSB;
    const rbt = qual === "SP" ? p.rbt12SP : p.rbt12BSB;
    const custos = qual === "SP" ? p.custos : p.custosBSB;
    const modo = qual === "SP" ? p.spModo : p.bsbModo;
    const sim = simples(rbt);
    if (!sim) return null;
    const das = fat * sim.aliq;
    const v = ivaForaAno(p, fat, custos, ano, sobre);
    if (ano <= 2026 || modo === "NORMAL") {
      return { das: das, iva: 0, debito: 0, credito: 0, iss: 0, irpj: 0,
        total: das, sim: sim, tAdv: v.tAdv, aliq: v.aliq, modo: ano <= 2026 ? "NORMAL" : modo };
    }
    if (modo === "HIB") {
      const dasResto = das * (SH_IRPJ + SH_ISS * v.aliq.iss);
      return { das: dasResto, iva: v.iva, debito: v.debito, credito: v.credito, iss: 0, irpj: 0,
        total: dasResto + v.iva, sim: sim, tAdv: v.tAdv, aliq: v.aliq, modo: modo };
    }
    /* REG: fora do Simples a partir de 2027 */
    const iss = (qual === "SP" ? issForaSP(p) : 0) * v.aliq.iss;
    const irpj = fat * p.irpj / 100;
    return { das: 0, iva: v.iva, debito: v.debito, credito: v.credito, iss: iss, irpj: irpj,
      total: v.iva + iss + irpj, sim: sim, tAdv: v.tAdv, aliq: v.aliq, modo: modo };
  }

  function simular(p) {
    const spHoje = cargaEscritorio(p, "SP", 2026);
    const bsbHoje = cargaEscritorio(p, "BSB", 2026);
    const hoje = spHoje.total + bsbHoje.total;
    const anos = ANOS.map(a => {
      const sp = cargaEscritorio(p, "SP", a), bsb = cargaEscritorio(p, "BSB", a);
      return { ano: a, sp: sp, bsb: bsb, total: sp.total + bsb.total, aliq: sp.aliq, tAdv: sp.tAdv };
    });
    return { spHoje: spHoje, bsbHoje: bsbHoje, hoje: hoje, anos: anos,
      fim: anos[anos.length - 1], tAdv33: (p.cbsRef + p.ibsRef) * (1 - p.red / 100) / 100 };
  }

  /* ============================ desenho ============================ */
  function parecer(s) {
    const dif = s.fim.total - s.hoje, piora = dif > 0;
    document.getElementById("parecer").style.setProperty("--cor-parecer",
      piora ? "var(--bad)" : "var(--good)");
    document.getElementById("p-cifra").textContent = F.sinal(dif) + "/mês";
    document.getElementById("p-texto").innerHTML =
      "É quanto a carga dos dois escritórios " + (piora ? "sobe" : "cai") +
      " em 2033 contra ficar tudo no Simples de hoje, mantidos os preços: de <strong>" +
      F.dinheiro(s.hoje) + "</strong> para <strong>" + F.dinheiro(s.fim.total) +
      "</strong> por mês, com SP no " + MODO[P.spModo] + " e Brasília no " + MODO[P.bsbModo] + ". " +
      (piora
        ? "O que se compra com essa diferença é o crédito para o cliente PJ — repassando o imposto por fora, quem exige crédito não paga mais por isso."
        : "Os créditos sobre os custos mais que compensam a mudança.");

    document.getElementById("i-sp").textContent =
      F.num1(s.spHoje.total / P.fatSP * 100) + "% → " + F.num1(s.fim.sp.total / P.fatSP * 100) + "%";
    document.getElementById("i-sp-nota").textContent =
      "hoje na faixa " + s.spHoje.sim.faixa + " do Anexo IV; em 2033 no " + MODO[P.spModo];
    document.getElementById("i-bsb").textContent =
      F.num1(s.bsbHoje.total / P.fatBSB * 100) + "% → " + F.num1(s.fim.bsb.total / P.fatBSB * 100) + "%";
    document.getElementById("i-bsb-nota").textContent =
      "hoje na faixa " + s.bsbHoje.sim.faixa + " do Anexo IV; em 2033 no " + MODO[P.bsbModo];
    document.getElementById("i-aliq").textContent = F.num2(s.tAdv33 * 100) + "% por fora";
    document.getElementById("i-aliq-nota").textContent =
      F.num1(P.cbsRef + P.ibsRef) + "% de referência com redução de " + F.num1(P.red) +
      "% — art. 127 da LC 214/2025";
    document.getElementById("i-cred").textContent =
      F.dinheiro(1000 * s.tAdv33 / (1 + s.tAdv33)) + " / R$ 1.000";

    document.getElementById("carimbo").innerHTML =
      "<div>Hoje<b>Os dois no Simples · Anexo IV</b></div>" +
      "<div>SP a partir de 2027<b>" + MODO[P.spModo] + "</b></div>" +
      "<div>Brasília a partir de 2027<b>" + MODO[P.bsbModo] + "</b></div>" +
      "<div>Alíquota-padrão de referência<b>" + F.num1(P.cbsRef + P.ibsRef) + "%</b></div>";
  }

  function tabelaAliquotas(s) {
    const red = 1 - P.red / 100;
    let h = "<thead><tr><th>Ano</th><th>CBS padrão</th><th>IBS padrão</th>" +
      "<th>Advocacia (−" + F.num1(P.red) + "%), por fora</th><th>ISS no cronograma</th>" +
      "<th>Carga SP</th><th>Carga BSB</th><th>Total do plano</th></tr></thead><tbody>";
    s.anos.forEach(c => {
      const a = c.aliq;
      h += "<tr" + (c.ano === 2033 ? ' class="realce"' : "") + "><td>" + c.ano +
        (a.teste ? " · teste" : "") + "</td><td>" + F.num2(a.cbs) + "%</td><td>" +
        F.num2(a.ibs) + "%</td><td>" +
        (a.teste ? "compensável com PIS/COFINS" : F.num2((a.cbs + a.ibs) * red) + "%") +
        "</td><td>" + (a.iss === 0 ? "extinto" : Math.round(a.iss * 100) + "% do atual") +
        "</td><td>" + F.dinheiro(c.sp.total) + "</td><td>" + F.dinheiro(c.bsb.total) +
        "</td><td>" + F.dinheiro(c.total) + " · " +
        F.num1(c.total / (P.fatSP + P.fatBSB) * 100) + "%</td></tr>";
    });
    document.getElementById("q-aliquotas").innerHTML = h + "</tbody>";
  }

  function demonstracao(s) {
    const sp = s.fim.sp, bsb = s.fim.bsb, tr = "—";
    const d = v => F.dinheiro(v);
    const cel = (c, val, dentro) => (c ? val : dentro || tr);
    const linha = (nome, a, b, c1, c2, classe) =>
      "<tr" + (classe ? ' class="' + classe + '"' : "") + "><td>" + nome + "</td><td>" +
      a + "</td><td>" + b + '</td><td style="border-left:1px solid var(--rule)">' + c1 +
      "</td><td>" + c2 + "</td></tr>";
    let h = "<thead><tr><th>Por mês</th><th>SP hoje</th><th>SP em 2033</th>" +
      '<th style="border-left:1px solid var(--rule)">Brasília hoje</th><th>Brasília em 2033</th></tr></thead><tbody>';
    h += linha("DAS do Simples (Anexo IV)",
      d(s.spHoje.das), cel(sp.das > 0, d(sp.das) + (P.spModo === "HIB" ? " · só a fatia de IRPJ/CSLL" : "")),
      d(s.bsbHoje.das), cel(bsb.das > 0, d(bsb.das) + (P.bsbModo === "HIB" ? " · só a fatia de IRPJ/CSLL" : "")));
    h += linha("IBS/CBS da advocacia (" + F.num2(s.tAdv33 * 100) + "% por fora, embutido)",
      tr, cel(sp.debito > 0, d(sp.debito)), tr, cel(bsb.debito > 0, d(bsb.debito)));
    h += linha("(−) Créditos sobre os custos",
      tr, cel(sp.debito > 0, F.contabil(-sp.credito)), tr, cel(bsb.debito > 0, F.contabil(-bsb.credito)));
    h += linha("IRPJ e CSLL (Lucro Presumido)",
      "dentro do DAS", cel(sp.irpj > 0, d(sp.irpj), "dentro do DAS"),
      "dentro do DAS", cel(bsb.irpj > 0, d(bsb.irpj), "dentro do DAS"));
    h += linha("Carga total", d(s.spHoje.total), d(sp.total), d(s.bsbHoje.total), d(bsb.total), "total");
    h += linha("Sobre o faturamento",
      F.num1(s.spHoje.total / P.fatSP * 100) + "%", F.num1(sp.total / P.fatSP * 100) + "%",
      F.num1(s.bsbHoje.total / P.fatBSB * 100) + "%", F.num1(bsb.total / P.fatBSB * 100) + "%", "realce");
    h += "</tbody>";
    document.getElementById("q-demo").innerHTML = h;
  }

  function cliente(s) {
    const t = s.tAdv33;
    const dentro = 1000 * t / (1 + t);      /* preço mantido: imposto embutido */
    const fora = 1000 * t;                  /* repasse: imposto além do preço */
    const d = v => F.dinheiro(v);
    const linha = (nome, destq, cred, pj, pf) =>
      "<tr><td>" + nome + "</td><td>" + destq + "</td><td>" + cred + "</td><td>" + pj +
      "</td><td>" + pf + "</td></tr>";
    /* No Simples normal pós-2033 o cliente credita a fatia de IBS/CBS
       embutida no DAS — aproximada pela partilha de consumo (~62%). */
    const credNormal = sim => 1000 * sim.aliq * (SH_PISCOF + SH_ISS);
    const linhaEscr = (nome, c, modo, sim) => {
      if (modo === "NORMAL") {
        return linha(nome + " — Simples normal", "—", "≈ " + d(credNormal(sim)) + " · fatia do DAS",
          "≈ " + d(1000 - credNormal(sim)), d(1000));
      }
      const rot = modo === "HIB" ? " — Simples híbrido" : " — regime com crédito";
      return linha(nome + rot + ", mantendo o preço", d(dentro), d(dentro), d(1000 - dentro), d(1000)) +
        linha(nome + rot + ", repassando por fora", d(fora), d(fora), d(1000), d(1000 + fora));
    };
    let h = "<thead><tr><th>De cada R$ 1.000 faturados</th><th>IBS/CBS destacado</th>" +
      "<th>Crédito do cliente PJ</th><th>Custo líquido · cliente PJ</th><th>Custo · PF ou Simples</th></tr></thead><tbody>";
    h += linha("Hoje — qualquer um dos dois, no Simples", "—", d(0), d(1000), d(1000));
    h += linhaEscr("SP em 2033", s.fim.sp, P.spModo, s.fim.sp.sim);
    h += linhaEscr("Brasília em 2033", s.fim.bsb, P.bsbModo, s.fim.bsb.sim);
    h += "</tbody>";
    document.getElementById("q-cliente").innerHTML = h;
  }

  /* Deslocar clientes sem exigência de crédito de SP para Brasília:
     cada cenário refaz os dois escritórios em 2033 com a receita
     deslocada e os RBT12 acompanhando. */
  function deslocamento(s) {
    const plano2033 = q => {
      const sp = cargaEscritorio(q, "SP", 2033), bsb = cargaEscritorio(q, "BSB", 2033);
      return sp && bsb ? { sp: sp, bsb: bsb, total: sp.total + bsb.total } : null;
    };
    const desloca = x => Object.assign({}, P, {
      fatSP: P.fatSP - x, rbt12SP: Math.max(0, P.rbt12SP - 12 * x),
      fatBSB: P.fatBSB + x, rbt12BSB: P.rbt12BSB + 12 * x
    });
    const base = plano2033(P);
    /* alíquotas marginais numéricas: o custo do último R$ 1.000/mês em cada praça */
    const mSP = base.sp.total - cargaEscritorio(desloca(1000), "SP", 2033).total;
    const cBSB1 = cargaEscritorio(desloca(1000), "BSB", 2033);
    const mBSB = cBSB1 ? cBSB1.total - base.bsb.total : null;

    const prosa = document.getElementById("p-desloca");
    prosa.innerHTML = mBSB == null
      ? "Brasília estouraria o teto do Simples já no primeiro deslocamento — não se aplica."
      : "Na margem, em 2033, cada R$ 1.000/mês que sai de São Paulo (" + MODO[P.spModo] +
        ") deixa de custar <strong>" + F.dinheiro(mSP) + "</strong> e passa a custar <strong>" +
        F.dinheiro(mBSB) + "</strong> em Brasília (" + MODO[P.bsbModo] + ", faixa " +
        base.bsb.sim.faixa + " do Anexo IV) — " +
        (mSP > mBSB ? "economia de <strong>" + F.dinheiro(mSP - mBSB) + " por R$ 1.000 deslocados</strong>"
          : "<strong>não há economia</strong> nesta configuração") +
        ", enquanto o RBT12 couber na faixa. Vale só para os clientes que <strong>não precisam do " +
        "crédito</strong>; quem exige crédito de IBS/CBS fica em SP.";

    let h = "<thead><tr><th>Deslocado para BSB</th><th>Carga SP 2033</th><th>Faixa BSB</th>" +
      "<th>Carga BSB 2033</th><th>Carga total</th><th>Economia por mês</th></tr></thead><tbody>";
    [0, 5000, 10000, 20000, 30000, 50000].filter(x => x <= P.fatSP - 10000).forEach(x => {
      const q = desloca(x);
      const sp = cargaEscritorio(q, "SP", 2033);
      const bsb = cargaEscritorio(q, "BSB", 2033);
      if (!bsb) {
        h += "<tr><td>" + F.dinheiro(x) + "/mês</td><td>" + F.dinheiro(sp.total) +
          '</td><td colspan="4">RBT12 de ' + F.dinheiro(q.rbt12BSB) +
          " estoura o teto de R$ 4,8 mi — Brasília sairia do Simples</td></tr>";
        return;
      }
      const eco = base.total - (sp.total + bsb.total);
      h += "<tr" + (x === 0 ? ' class="realce"' : "") + "><td>" + F.dinheiro(x) + "/mês</td><td>" +
        F.dinheiro(sp.total) + "</td><td>" + bsb.sim.faixa + " · " + F.num2(bsb.sim.aliq * 100) +
        "% efetiva</td><td>" + F.dinheiro(bsb.total) + "</td><td>" + F.dinheiro(sp.total + bsb.total) +
        '</td><td class="' + (eco >= 0 ? "pos" : "neg") + '">' + F.sinal(eco) + "</td></tr>";
    });
    document.getElementById("q-desloca").innerHTML = h + "</tbody>";
  }

  /* Barras: todas as combinações pós-reforma em 2033 contra hoje.
     Cada barra empilha SP + Brasília, cada CNPJ na sua faixa do Anexo IV. */
  function barrasOpcoes(s) {
    const combos = [
      { hoje: true, rot: "Hoje — os dois no Simples" },
      { sp: "NORMAL", bsb: "NORMAL" },
      { sp: "NORMAL", bsb: "HIB" },
      { sp: "HIB", bsb: "NORMAL" },
      { sp: "HIB", bsb: "HIB" },
      { sp: "REG", bsb: "NORMAL" },
      { sp: "REG", bsb: "HIB" }
    ];
    combos.forEach(cb => {
      if (cb.hoje) { cb.vSP = s.spHoje.total; cb.vBSB = s.bsbHoje.total; return; }
      const q = Object.assign({}, P, { spModo: cb.sp, bsbModo: cb.bsb });
      cb.vSP = cargaEscritorio(q, "SP", 2033).total;
      cb.vBSB = cargaEscritorio(q, "BSB", 2033).total;
      cb.rot = "SP " + MODO[cb.sp] + " · BSB " + MODO[cb.bsb];
      cb.atual = cb.sp === P.spModo && cb.bsb === P.bsbModo;
    });

    const svg = document.getElementById("g-opcoes");
    C.limpar(svg);
    const L = 880, rowH = 52, mt = 26, me = 14, md = 168;
    const A = mt + combos.length * rowH + 30;
    svg.setAttribute("viewBox", "0 0 " + L + " " + A);
    const maxV = Math.max.apply(null, combos.map(c => c.vSP + c.vBSB)) * 1.06 || 1;
    const X = v => me + v / maxV * (L - me - md);
    const cA = C.cor("--serie-a"), cB = C.cor("--serie-b"), cInk = C.cor("--ink"),
      cM = C.cor("--ink-2"), cF = C.cor("--ink-3"), cPos = C.cor("--good"), cNeg = C.cor("--bad");

    const hoje = combos[0].vSP + combos[0].vBSB;
    C.el("line", { x1: X(hoje), x2: X(hoje), y1: mt - 12, y2: A - 22, stroke: cF,
      "stroke-width": 1, "stroke-dasharray": "4 3" }, svg);
    C.el("text", { x: X(hoje), y: mt - 16, "text-anchor": "middle", fill: cF, "font-size": 10,
      "font-family": "var(--sans)", "letter-spacing": ".09em" }, svg).textContent = "HOJE";

    combos.forEach((cb, i) => {
      const y = mt + i * rowH, total = cb.vSP + cb.vBSB, dif = total - hoje;
      C.el("text", { x: me, y: y + 11, fill: cb.atual ? cInk : cM, "font-size": 12,
        "font-family": "var(--sans)", "font-weight": cb.atual || cb.hoje ? 700 : 400 }, svg)
        .textContent = cb.rot + (cb.atual ? "  — plano configurado" : "");
      const yb = y + 18, hb = 15;
      C.el("rect", { x: me, y: yb, width: Math.max(1, X(cb.vSP) - me), height: hb,
        fill: cb.hoje ? cF : cA, rx: 2 }, svg);
      C.el("rect", { x: X(cb.vSP), y: yb, width: Math.max(1, X(cb.vSP + cb.vBSB) - X(cb.vSP)),
        height: hb, fill: cb.hoje ? C.cor("--rule-strong") : cB, rx: 2 }, svg);
      if (cb.atual) {
        C.el("rect", { x: me - 3, y: yb - 3, width: X(total) - me + 6, height: hb + 6,
          fill: "none", stroke: cInk, "stroke-width": 1.5 }, svg);
      }
      C.el("text", { x: X(total) + 9, y: yb + 12, fill: cInk, "font-size": 12.5, "font-weight": 600,
        "font-family": "var(--mono)", "font-variant-numeric": "tabular-nums" }, svg)
        .textContent = F.dinheiro(total);
      if (!cb.hoje && Math.abs(dif) >= 1) {
        C.el("text", { x: X(total) + 9, y: yb + 27, fill: dif > 0 ? cNeg : cPos, "font-size": 11,
          "font-family": "var(--mono)", "font-variant-numeric": "tabular-nums" }, svg)
          .textContent = (dif > 0 ? "+" : "−") + F.dinheiro(Math.abs(dif));
      }
    });
  }

  function memorial(s) {
    let h = "<thead><tr><th>Ano</th><th>Alíquota advocacia</th><th>SP · DAS</th><th>SP · IBS/CBS líq.</th>" +
      "<th>SP · ISS + IRPJ/CSLL</th><th>Carga SP</th><th>Carga BSB</th><th>Total</th><th>Contra hoje</th></tr></thead><tbody>";
    s.anos.forEach(a => {
      const dif = s.hoje - a.total; /* positivo = o plano alivia */
      h += "<tr><td>" + a.ano + (a.ano === 2026 ? " · teste" : "") + "</td><td>" +
        (a.aliq.teste ? "—" : F.num2(a.tAdv * 100) + "%") + "</td><td>" +
        (a.sp.das > 0 ? F.dinheiro(a.sp.das) : "—") + "</td><td>" +
        (a.sp.debito > 0 ? F.dinheiro(a.sp.iva) : "—") + "</td><td>" +
        (a.sp.irpj > 0 ? F.dinheiro(a.sp.iss + a.sp.irpj) : "—") + "</td><td>" +
        F.dinheiro(a.sp.total) + "</td><td>" + F.dinheiro(a.bsb.total) + "</td><td>" +
        F.dinheiro(a.total) + '</td><td class="' + (dif >= 0 ? "pos" : "neg") + '">' +
        F.sinal(dif) + "</td></tr>";
    });
    document.getElementById("q-anos").innerHTML = h + "</tbody>";
  }

  function desenhar() {
    const s = simular(P);
    parecer(s); barrasOpcoes(s); tabelaAliquotas(s); demonstracao(s); cliente(s); deslocamento(s); memorial(s);

    /* campos que só fazem sentido em alguns caminhos */
    document.getElementById("c-iss").closest("fieldset").style.display =
      P.spModo === "REG" ? "" : "none";
    document.getElementById("c-iss").closest(".campo").style.display =
      P.issModo === "PCT" ? "" : "none";
    document.getElementById("c-issFixo").closest(".campo").style.display =
      P.issModo === "SUP" ? "" : "none";
    document.getElementById("c-irpj").closest(".campo").style.display =
      P.spModo === "REG" ? "" : "none";
    document.getElementById("c-custos").closest(".campo").style.display =
      P.spModo === "NORMAL" ? "none" : "";
    document.getElementById("c-custosBSB").closest(".campo").style.display =
      P.bsbModo === "HIB" ? "" : "none";

    C.quadroColunas({
      svg: "g-transicao", tela: "t-transicao", dica: "d-transicao",
      dados: s.anos.map(a => ({ ano: a.ano, a: a.total, b: s.hoje,
        sp: a.sp.total, bsb: a.bsb.total, tAdv: a.tAdv, teste: a.aliq.teste })),
      corA: "--serie-a", corB: "--serie-b",
      rotuloA: "Com o plano", rotuloB: "Tudo no Simples",
      extraDica: d => C.linhaDica("SP", F.dinheiro(d.sp)) + C.linhaDica("Brasília", F.dinheiro(d.bsb)) +
        C.linhaDica("Alíquota da advocacia",
          d.teste ? "teste compensável" : F.num2(d.tAdv * 100) + "% por fora") +
        C.linhaDica(d.a <= d.b ? "O plano alivia" : "O plano pesa",
          F.sinal(s.hoje - d.a), null, d.a <= d.b ? "pos" : "neg")
    });

    const lin = [30, 25, 20, 15, 10, 5, 0].map(v => ({ valor: v, rotulo: v + "%" }));
    const cpAtual = Math.min(30, Math.max(0, Math.round(P.custos / P.fatSP * 100 / 5) * 5));
    lin.forEach(l => { l.marcada = l.valor === cpAtual; });
    const refTotal = P.cbsRef + P.ibsRef;
    const col = [];
    for (let j = -3; j <= 3; j++) col.push({ valor: +(refTotal + j).toFixed(1) });
    col.forEach(c => { c.rotulo = F.num1(c.valor) + "%"; c.marcada = c.valor === +refTotal.toFixed(1); });
    C.quadroCalor({
      svg: "g-calor", tela: "t-calor", dica: "d-calor", faixa: "faixa-calor",
      linhas: lin, colunas: col,
      celula: (cp, al) => {
        const q = Object.assign({}, P, { custos: P.fatSP * cp / 100 });
        const sp = cargaEscritorio(q, "SP", 2033, { aliqTotal: al });
        const bsb = cargaEscritorio(q, "BSB", 2033, { aliqTotal: al });
        return s.hoje - (sp.total + bsb.total);
      },
      tituloX: "ALÍQUOTA-PADRÃO DE REFERÊNCIA (IBS + CBS)",
      tituloY: "CUSTOS DE SP COM CRÉDITO (% DO FATURAMENTO)",
      rotuloDif: "Alívio do plano",
      dicaTitulo: (l, c) => "Custos de " + l.valor + "% · referência de " + F.num1(c.valor) + "%",
      dicaExtra: v => C.linhaDica("Carga do plano em 2033", F.dinheiro(s.hoje - v) + "/mês"),
      rodape: "Cada célula: carga mensal de hoje (tudo no Simples) menos a do plano em 2033, mantidos os preços. Azul = o plano alivia."
    });
  }

  const render = C.agendador(desenhar);
  const painel = C.montarPainel(SPEC, P, "campos", render);
  const sincSP = C.ligarSeletor("spModo", P, "spModo", render);
  const sincBSB = C.ligarSeletor("bsbModo", P, "bsbModo", render);
  const sincISS = C.ligarSeletor("issModo", P, "issModo", render);
  document.getElementById("restaurar").addEventListener("click", () => {
    painel.restaurar(PADRAO);
    sincSP(PADRAO.spModo); sincBSB(PADRAO.bsbModo); sincISS(PADRAO.issModo);
    render();
  });

  desenhar();
  C.observarTema(render);
})();
