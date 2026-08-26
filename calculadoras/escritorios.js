/* A reforma tributária nos dois escritórios — motor e montagem da página. */
(function () {
  "use strict";
  const C = window.Calc, F = C.Fmt;

  const SPEC = [
    { g: "Escritório de São Paulo", campos: [
      { m: 1, k: "fatSP", r: "Faturamento", un: "R$/mês", min: 10000, max: 1000000, passo: 5000, v: 100000 },
      { k: "pisCof", r: "PIS e COFINS hoje", un: "%", min: 0, max: 10, passo: 0.05, v: 3.65,
        aj: "Regime cumulativo do Lucro Presumido: 0,65% + 3%." },
      { k: "irpj", r: "IRPJ e CSLL efetivos", un: "%", min: 0, max: 20, passo: 0.01, v: 7.68,
        aj: "Presunção de 32% × (15% + 9%). Não mudam com a reforma; o adicional de 10% do IRPJ, se houver, entra aqui." },
      { k: "iss", r: "ISS hoje", un: "%", min: 0, max: 5, passo: 0.25, v: 5,
        aj: "Sociedade uniprofissional com ISS fixo? Converta o valor pago para % da receita." },
      { m: 1, k: "custos", r: "Custos que geram crédito", un: "R$/mês", min: 0, max: 500000, passo: 500, v: 15000,
        aj: "Aluguel, energia, software, contabilidade — despesas com nota de fornecedor no regime regular. Folha e pró-labore não geram crédito." }
    ]},
    { g: "Escritório de Brasília", campos: [
      { m: 1, k: "fatBSB", r: "Faturamento", un: "R$/mês", min: 1000, max: 400000, passo: 1000, v: 30000,
        aj: "Entre R$ 20 e 40 mil por mês, pela faixa citada." },
      { m: 1, k: "rbt12", r: "Receita dos últimos 12 meses", un: "R$", min: 0, max: 4800000, passo: 10000, v: 360000,
        aj: "O RBT12, que define a faixa do Anexo IV. O padrão equivale a 12 × R$ 30 mil." }
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
  const P = Object.assign({}, PADRAO);

  const ANOS = [2026, 2027, 2028, 2029, 2030, 2031, 2032, 2033];

  /* ============================ motor ============================ */
  /* Fração vigente de cada tributo no ano, conforme EC 132/2023.
     2026 é ano-teste (0,9% + 0,1% compensáveis com PIS/COFINS): carga
     prática igual à de hoje, então entra como o sistema atual puro. */
  function fase(ano) {
    if (ano <= 2026) return { cbs: 0, ibs: 0, iss: 1, pisCof: 1 };
    if (ano <= 2028) return { cbs: 1, ibs: 0, iss: 1, pisCof: 0 };
    if (ano <= 2032) {
      const n = ano - 2028; /* 1..4 */
      return { cbs: 1, ibs: 0.1 * n, iss: 1 - 0.1 * n, pisCof: 0 };
    }
    return { cbs: 1, ibs: 1, iss: 0, pisCof: 0 };
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
        return { aliq: Math.max(0, (base * ANEXO4[i][1] - ANEXO4[i][2]) / base), faixa: i + 1 };
      }
    }
    return null; /* acima do teto de R$ 4,8 mi */
  }

  /* Carga mensal do escritório de SP num ano do cronograma, mantido o
     preço final (IBS/CBS embutidos: t/(1+t)). sobre = {aliqTotal, custosPct}
     para a sensibilidade. */
  function cargaSP(p, ano, sobre) {
    sobre = sobre || {};
    const refTotal = p.cbsRef + p.ibsRef;
    const fator = sobre.aliqTotal != null ? sobre.aliqTotal / refTotal : 1;
    const custos = sobre.custosPct != null ? p.fatSP * sobre.custosPct / 100 : p.custos;
    const f = fase(ano);
    const vig = (p.cbsRef * f.cbs + p.ibsRef * f.ibs) * fator / 100; /* alíquota-padrão vigente */
    const tAdv = vig * (1 - p.red / 100);
    const debito = p.fatSP * tAdv / (1 + tAdv);
    const credito = Math.min(debito, custos * vig / (1 + vig));
    const iva = Math.max(0, debito - credito);
    const pis = p.fatSP * p.pisCof / 100 * f.pisCof;
    const issV = p.fatSP * p.iss / 100 * f.iss;
    const irpjV = p.fatSP * p.irpj / 100;
    return { debito: debito, credito: credito, iva: iva, pis: pis, iss: issV, irpj: irpjV,
      total: iva + pis + issV + irpjV, tAdv: tAdv, vig: vig };
  }

  const hojeSP = p => p.fatSP * (p.pisCof + p.irpj + p.iss) / 100;

  function simular(p) {
    const hoje = hojeSP(p);
    const anos = ANOS.map(a => Object.assign({ ano: a }, cargaSP(p, a)));
    const fim = anos[anos.length - 1];
    const sim = simples(p.rbt12);
    const das = sim ? p.fatBSB * sim.aliq : null;
    return { hoje: hoje, anos: anos, fim: fim, sim: sim, das: das,
      tAdv33: (p.cbsRef + p.ibsRef) * (1 - p.red / 100) / 100 };
  }

  /* ============================ desenho ============================ */
  function parecer(s) {
    const dif = s.fim.total - s.hoje, piora = dif > 0;
    document.getElementById("parecer").style.setProperty("--cor-parecer",
      piora ? "var(--bad)" : "var(--good)");
    document.getElementById("p-cifra").textContent = F.sinal(dif) + "/mês";
    document.getElementById("p-texto").innerHTML =
      "É quanto a carga mensal de São Paulo " + (piora ? "sobe" : "cai") +
      " no regime completo se o escritório absorver o IBS/CBS no preço atual: de <strong>" +
      F.dinheiro(s.hoje) + "</strong> para <strong>" + F.dinheiro(s.fim.total) +
      "</strong> por mês. Brasília segue no Simples, com DAS " +
      (s.das == null ? "fora do teto — confira o RBT12" : "de <strong>" + F.dinheiro(s.das) + "</strong>") +
      ", que a reforma mantém. " + (piora
        ? "Repassando o imposto por fora, a carga própria volta ao patamar de hoje — e o cliente PJ recupera tudo como crédito."
        : "Os créditos sobre os custos mais que compensam a alíquota nova.");

    document.getElementById("i-sp").textContent =
      F.num1(s.hoje / P.fatSP * 100) + "% → " + F.num1(s.fim.total / P.fatSP * 100) + "%";
    document.getElementById("i-bsb").textContent =
      s.sim == null ? "fora do teto" : F.num2(s.sim.aliq * 100) + "%";
    document.getElementById("i-bsb-nota").textContent = s.sim == null
      ? "RBT12 acima de R$ 4,8 milhões não cabe no Simples"
      : "faixa " + s.sim.faixa + " do Anexo IV · DAS de " + F.dinheiro(s.das) + " por mês";
    document.getElementById("i-aliq").textContent = F.num2(s.tAdv33 * 100) + "% por fora";
    document.getElementById("i-aliq-nota").textContent =
      F.num1(P.cbsRef + P.ibsRef) + "% de referência com redução de " + F.num1(P.red) +
      "% — art. 127 da LC 214/2025";
    document.getElementById("i-cred").textContent =
      F.dinheiro(1000 * s.tAdv33 / (1 + s.tAdv33)) + " / R$ 1.000";

    document.getElementById("carimbo").innerHTML =
      "<div>São Paulo hoje<b>Lucro Presumido · ISS " + F.num1(P.iss) + "%</b></div>" +
      "<div>Brasília<b>Simples Nacional · Anexo IV</b></div>" +
      "<div>Alíquota-padrão de referência<b>" + F.num1(P.cbsRef + P.ibsRef) + "%</b></div>" +
      "<div>Regime completo<b>2033</b></div>";
  }

  function demonstracao(s) {
    const c = s.fim, tr = "—";
    const linha = (nome, a, b, c1, c2, classe) =>
      "<tr" + (classe ? ' class="' + classe + '"' : "") + "><td>" + nome + "</td><td>" +
      a + "</td><td>" + b + '</td><td style="border-left:1px solid var(--rule)">' + c1 +
      "</td><td>" + c2 + "</td></tr>";
    const d = v => F.dinheiro(v);
    let h = "<thead><tr><th>Por mês</th><th>SP hoje</th><th>SP em 2033</th>" +
      '<th style="border-left:1px solid var(--rule)">Brasília hoje</th><th>Brasília em 2033</th></tr></thead><tbody>';
    h += linha("PIS e COFINS", d(P.fatSP * P.pisCof / 100), d(0), tr, tr);
    h += linha("ISS (" + F.num1(P.iss) + "%)", d(P.fatSP * P.iss / 100), d(0), tr, tr);
    h += linha("IBS + CBS da advocacia (" + F.num2(c.tAdv * 100) + "% por fora, embutido)", d(0), d(c.debito), tr, tr);
    h += linha("(−) Créditos sobre os custos", d(0), F.contabil(-c.credito), tr, tr);
    h += linha("DAS do Simples" + (s.sim ? " (Anexo IV, faixa " + s.sim.faixa + ")" : ""), tr, tr,
      s.das == null ? "fora do teto" : d(s.das), s.das == null ? "fora do teto" : d(s.das));
    h += linha("Tributos sobre a receita",
      d(P.fatSP * (P.pisCof + P.iss) / 100), d(c.iva),
      s.das == null ? tr : d(s.das), s.das == null ? tr : d(s.das), "soma");
    h += linha("IRPJ e CSLL (Lucro Presumido)", d(c.irpj), d(c.irpj), "dentro do DAS", "dentro do DAS");
    h += linha("Carga total", d(s.hoje), d(c.total),
      s.das == null ? tr : d(s.das), s.das == null ? tr : d(s.das), "total");
    h += linha("Sobre o faturamento",
      F.num1(s.hoje / P.fatSP * 100) + "%", F.num1(c.total / P.fatSP * 100) + "%",
      s.sim == null ? tr : F.num2(s.sim.aliq * 100) + "%",
      s.sim == null ? tr : F.num2(s.sim.aliq * 100) + "%", "realce");
    h += "</tbody>";
    document.getElementById("q-demo").innerHTML = h;
  }

  function cliente(s) {
    const t = s.tAdv33;
    const dentro = 1000 * t / (1 + t);      /* preço mantido: imposto embutido */
    const fora = 1000 * t;                  /* repasse: imposto além do preço */
    /* No Simples o adquirente só credita a parcela de IBS/CBS embutida no
       DAS — aproximada aqui pela fatia de ISS/ICMS do Anexo IV, ~40%. */
    const credSimples = s.sim ? 1000 * s.sim.aliq * 0.4 : 0;
    const linha = (nome, destq, cred, pj, pf) =>
      "<tr><td>" + nome + "</td><td>" + destq + "</td><td>" + cred + "</td><td>" + pj +
      "</td><td>" + pf + "</td></tr>";
    const d = v => F.dinheiro(v);
    let h = "<thead><tr><th>De cada R$ 1.000 faturados</th><th>IBS/CBS destacado</th>" +
      "<th>Crédito do cliente PJ</th><th>Custo líquido · cliente PJ</th><th>Custo · PF ou Simples</th></tr></thead><tbody>";
    h += linha("SP hoje (Presumido, sem destaque)", "—", d(0), d(1000), d(1000));
    h += linha("SP em 2033, mantendo o preço", d(dentro), d(dentro), d(1000 - dentro), d(1000));
    h += linha("SP em 2033, repassando por fora", d(fora), d(fora), d(1000), d(1000 + fora));
    h += linha("Brasília no Simples (crédito ≈ 40% do DAS)",
      s.sim ? "≈ " + d(credSimples) : "—", s.sim ? "≈ " + d(credSimples) : "—",
      s.sim ? "≈ " + d(1000 - credSimples) : "—", d(1000));
    h += "</tbody>";
    document.getElementById("q-cliente").innerHTML = h;
  }

  function memorial(s) {
    let h = "<thead><tr><th>Ano</th><th>IBS/CBS líquido</th><th>Créditos usados</th><th>PIS/COFINS</th>" +
      "<th>ISS</th><th>IRPJ/CSLL</th><th>Carga de SP</th><th>Contra hoje</th></tr></thead><tbody>";
    s.anos.forEach(a => {
      const dif = s.hoje - a.total; /* positivo = a reforma alivia */
      h += "<tr><td>" + a.ano + (a.ano === 2026 ? " · teste" : "") + "</td><td>" + F.dinheiro(a.iva) +
        "</td><td>" + F.contabil(-a.credito) + "</td><td>" + F.dinheiro(a.pis) + "</td><td>" +
        F.dinheiro(a.iss) + "</td><td>" + F.dinheiro(a.irpj) + "</td><td>" + F.dinheiro(a.total) +
        '</td><td class="' + (dif >= 0 ? "pos" : "neg") + '">' + F.sinal(dif) + "</td></tr>";
    });
    document.getElementById("q-anos").innerHTML = h + "</tbody>";
  }

  function desenhar() {
    const s = simular(P);
    parecer(s); demonstracao(s); cliente(s); memorial(s);

    C.quadroColunas({
      svg: "g-transicao", tela: "t-transicao", dica: "d-transicao",
      dados: s.anos.map(a => ({ ano: a.ano, a: a.total, b: s.hoje, iva: a.iva })),
      corA: "--serie-a", corB: "--serie-b",
      rotuloA: "Com a reforma", rotuloB: "Sistema de hoje",
      extraDica: d => C.linhaDica(d.a <= d.b ? "A reforma alivia" : "A reforma pesa",
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
      celula: (cp, al) => s.hoje - cargaSP(P, 2033, { aliqTotal: al, custosPct: cp }).total,
      tituloX: "ALÍQUOTA-PADRÃO DE REFERÊNCIA (IBS + CBS)",
      tituloY: "CUSTOS COM CRÉDITO (% DO FATURAMENTO)",
      rotuloDif: "Alívio com a reforma",
      dicaTitulo: (l, c) => "Custos de " + l.valor + "% · referência de " + F.num1(c.valor) + "%",
      dicaExtra: v => C.linhaDica("Carga de SP em 2033",
        F.dinheiro(s.hoje - v) + "/mês"),
      rodape: "Cada célula: carga mensal de hoje menos a de 2033, mantido o preço. Azul = a reforma alivia."
    });
  }

  const render = C.agendador(desenhar);
  const painel = C.montarPainel(SPEC, P, "campos", render);
  document.getElementById("restaurar").addEventListener("click", () => {
    painel.restaurar(PADRAO);
    render();
  });

  desenhar();
  C.observarTema(render);
})();
