function render() {
  document.getElementById('updateTime').innerText = data.updateTime;
  document.getElementById('pcr').innerText = data.current.pcr;
  document.getElementById('vix').innerText = data.current.vix;
  document.getElementById('ltp').innerText = data.current.ltp.toLocaleString('en-IN');

  // Logic for Active Bias Color
  const ltp = data.current.ltp;
  const vwap = data.v11.m;
  const biasBox = document.querySelector('.bias-box');
  const biasVal = document.getElementById('activeBias');

  if (ltp > vwap) {
    biasVal.innerText = "Bullish Lean";
    biasVal.style.color = "#10b981"; // Green
  } else {
    biasVal.innerText = "Bearish Lean";
    biasVal.style.color = "#ef4444"; // Red
  }

  // Update Structure Engine with real calculated values
  document.getElementById('bigCandle').innerText = data.structure.big;
  document.getElementById('sameColor').innerText = data.structure.same;
  document.getElementById('overlap').innerText = data.structure.overlap;

  // Rest of your rendering code...
  document.getElementById('s_vwap_bias').innerText = ltp > vwap ? "Strong Above" : "Weak Below";
  document.getElementById('s_gap').innerText = (ltp - vwap).toFixed(2);
}
