// infer.js — 서버 없이 브라우저에서 해충 분류 추론.
// data/model.json 의 float 가중치로 forward 를 그대로 재현한다(서버 tflite 와 argmax 동일).
//   tokens(32) → Embedding(mask_zero) → masked GlobalAvgPool → Dense(32,relu) → Dense(7) → softmax
// Node 에서도 테스트할 수 있게 globalThis.PestModel 로도 노출.
(function (root) {
  let M = null;          // model.json + info
  let VOCAB = null;      // token -> index
  // Keras TextVectorization "lower_and_strip_punctuation" 과 동일한 구두점 제거(공백으로 치환 X, 삭제).
  const PUNCT = /[!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]/g;

  async function loadModel(modelUrl, infoUrl) {
    modelUrl = modelUrl || "data/model.json";
    infoUrl = infoUrl || "data/pest_info.json";
    const [m, info] = await Promise.all([
      fetch(modelUrl).then((r) => r.json()),
      fetch(infoUrl).then((r) => r.json()),
    ]);
    setModel(m, info);
    return M;
  }

  // Node 테스트용: 이미 읽은 객체를 직접 주입.
  function setModel(m, info) {
    M = m;
    M.info = info || {};
    VOCAB = new Map();
    m.vocab.forEach((tok, i) => { if (i >= 2) VOCAB.set(tok, i); }); // 0='' , 1='[UNK]'
  }

  function tokenize(text) {
    const cleaned = String(text).toLowerCase().replace(PUNCT, "");
    const words = cleaned.split(/\s+/).filter(Boolean);
    const ids = new Array(M.seq_len).fill(0);                 // post-padding 0
    const n = Math.min(words.length, M.seq_len);              // post-truncate
    for (let i = 0; i < n; i++) {
      ids[i] = VOCAB.has(words[i]) ? VOCAB.get(words[i]) : 1; // OOV → [UNK]=1
    }
    return ids;
  }

  function softmax(v) {
    const mx = Math.max.apply(null, v);
    const e = v.map((x) => Math.exp(x - mx));
    const s = e.reduce((a, b) => a + b, 0);
    return e.map((x) => x / s);
  }

  function forward(ids) {
    const D = M.emb[0].length;                 // 32
    const pooled = new Array(D).fill(0);
    let cnt = 0;
    for (let k = 0; k < ids.length; k++) {
      const t = ids[k];
      if (t === 0) continue;                   // padding masked out
      const row = M.emb[t];
      for (let d = 0; d < D; d++) pooled[d] += row[d];
      cnt++;
    }
    if (cnt > 0) for (let d = 0; d < D; d++) pooled[d] /= cnt;

    const h = M.d1W.map((w, o) => {            // Dense(32) + relu
      let s = M.d1b[o];
      for (let i = 0; i < D; i++) s += w[i] * pooled[i];
      return s > 0 ? s : 0;
    });
    const logits = M.d2W.map((w, o) => {       // Dense(7)
      let s = M.d2b[o];
      for (let i = 0; i < h.length; i++) s += w[i] * h[i];
      return s;
    });
    return softmax(logits);
  }

  function predict(text) {
    const probs = forward(tokenize(text));
    let bi = 0;
    for (let i = 1; i < probs.length; i++) if (probs[i] > probs[bi]) bi = i;
    const en = M.label_map[String(bi)];
    const order = [];
    for (let i = 0; i < probs.length; i++) order.push(M.label_map[String(i)]);
    const pairs = order
      .map((o, i) => ({ en: o, kr: M.kor[o] || o, p: probs[i] }))
      .sort((a, b) => b.p - a.p);
    return {
      text: String(text),
      pest_en: en,
      pest_kr: M.kor[en] || en,
      confidence: Math.max.apply(null, probs),
      probs: pairs,
      info: M.info[en] || null,
    };
  }

  root.PestModel = { loadModel, setModel, predict, tokenize };
})(typeof window !== "undefined" ? window : globalThis);
