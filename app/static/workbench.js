(function () {
  var state = { payload: null, kind: 'bars', run: null, approved: false };
  var $ = function (id) { return document.getElementById(id); };
  function esc(value) {
    return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, function (ch) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch];
    });
  }
  async function request(url, options) {
    var response = await fetch(url, Object.assign({headers: {'Content-Type': 'application/json'}}, options || {}));
    var data = await response.json().catch(function () { return {}; });
    if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
    return data;
  }
  function setNotice(text) { $('notice').textContent = text || ''; }
  function renderIssues(data) {
    $('issue-count').textContent = data.issues.length + ' 条';
    $('issue-list').innerHTML = data.issues.length ? data.issues.map(function (item) {
      return '<li><span>' + esc(item.line || '-') + '</span><span>' + esc(item.key || '无主键') + '</span><code>' + esc(item.code) + '</code></li>';
    }).join('') : '<li class="empty">暂无异常</li>';
  }
  function renderBreakdown(items) {
    if (!items || !items.length) return '';
    return '<details><summary>' + items.length + ' 项</summary><ul>' + items.map(function (item) {
      return '<li>' + esc(item) + '</li>';
    }).join('') + '</ul></details>';
  }
  function renderRows(data) {
    var labels = Object.assign({label: '记录'}, state.resultColumns);
    var source = data.row_kind === 'source';
    var hasBreakdown = data.rows.some(function (row) { return row.breakdown && row.breakdown.length; });
    var keys = source ? state.inputColumns : Object.keys(labels).filter(function (key) {
      return data.rows.some(function (row) { return Object.hasOwn(row, key); });
    });
    $('row-count').textContent = source ? data.rows.length + ' 行预览' :
      data.summary.PASS + ' 通过 / ' + data.summary.REVIEW + ' 复核 / ' + data.summary.REJECT + ' 阻断';
    var tail = source ? '' : '<th>结论</th>' + (hasBreakdown ? '<th>计算分项</th>' : '');
    $('row-head').innerHTML = '<tr>' + keys.map(function (key) { return '<th>' + esc(labels[key] || key) + '</th>'; }).join('') + tail + '</tr>';
    $('row-body').innerHTML = data.rows.length ? data.rows.map(function (row) {
      var values = keys.map(function (key) { return '<td class="' + (typeof row[key] === 'number' ? 'num' : '') + '">' + esc(row[key]) + '</td>'; }).join('');
      var verdict = source ? '' : '<td><span class="verdict" data-v="' + esc(row.verdict) + '">' + esc(row.verdict || '') + '</span><br><small>' + esc(row.reason || '') + '</small></td>';
      var breakdown = hasBreakdown ? '<td>' + renderBreakdown(row.breakdown) + '</td>' : '';
      return '<tr>' + values + verdict + breakdown + '</tr>';
    }).join('') : '<tr><td class="empty" colspan="' + (keys.length + (source ? 0 : 1)) + '">没有可展示条目</td></tr>';
  }
  function renderLedger(data) {
    if (!data.ledger) { $('ledger-list').innerHTML = '<p class="empty">运行对账后显示</p>'; return; }
    var values = data.ledger;
    var correction = values.correction || { counted: 0, isolated: 0 };
    $('ledger-list').innerHTML = [
      ['来源行', values.counts.input], ['采信行', values.counts.accepted], ['隔离行', values.counts.isolated],
      ['精确重复', values.counts.duplicates], ['忽略行', values.counts.ignored], ['计算条目', values.counts.computed],
      ['补正计入', correction.counted], ['仍隔离', correction.isolated]
    ].map(function (row) { return '<div class="ledger-row"><span>' + row[0] + '</span><strong>' + row[1] + '</strong></div>'; }).join('') +
      '<div class="ledger-row"><span>' + esc(values.metric_field) + '</span><strong>' + esc(values.metric_total) + '</strong></div>' +
      values.checks.map(function (check) { return '<div class="ledger-row"><span>' + esc(check.label) + '</span><strong class="' + (check.ok ? 'check-ok' : 'check-bad') + '">' + (check.ok ? '通过' : '异常') + '</strong></div>'; }).join('');
  }
  var STATE_LABEL = { counted: '已计入', isolated: '隔离', duplicate: '重复', ignored: '忽略' };
  function renderReconcile(data) {
    var correction = data.ledger && data.ledger.correction;
    if (!correction) {
      $('reconcile-count').textContent = '--';
      $('reconcile-head').innerHTML = '';
      $('reconcile-body').innerHTML = '<tr><td class="empty">运行对账后显示</td></tr>';
      return;
    }
    var rows = correction.rows || [];
    $('reconcile-count').textContent = correction.counted + ' 已计入 / ' + correction.isolated + ' 隔离 / ' + rows.length + ' 原始行';
    $('reconcile-head').innerHTML = '<tr><th>行</th><th>分段</th><th>原始读数</th><th>当前读数</th><th>状态</th><th>原因</th></tr>';
    $('reconcile-body').innerHTML = rows.map(function (row) {
      var changed = row.corrected && (row.original.temp_c !== row.current.temp_c || row.original.unit !== row.current.unit ||
        row.original.segment_end !== row.current.segment_end || row.original.segment_start !== row.current.segment_start);
      var status = STATE_LABEL[row.state] || row.state;
      if (row.correction && row.correction.status === 'REJECTED') status += ' · 补正被拒';
      return '<tr>' +
        '<td class="num">' + esc(row.line) + (row.corrected ? ' <b class="fix-mark">改</b>' : '') + '</td>' +
        '<td>' + esc(row.key || '无主键') + '</td>' +
        '<td>' + esc(row.original.temp_c || '—') + ' ' + esc(row.original.unit || '') + '</td>' +
        '<td class="' + (changed ? 'changed' : '') + '">' + esc(row.current.temp_c || '—') + ' ' + esc(row.current.unit || '') + '</td>' +
        '<td>' + esc(status) + '</td>' +
        '<td><code>' + esc(row.correction && row.correction.reason ? row.correction.reason : (row.code || '')) + '</code></td>' +
        '</tr>';
    }).join('') || '<tr><td class="empty" colspan="6">没有来源行</td></tr>';
  }
  function renderCorrections(data) {
    var list = data.corrections || [];
    $('correction-count').textContent = list.length + ' 次补正';
  }
  function render(data) {
    state.payload = data;
    $('chart-label').textContent = Object.values(state.resultColumns)[0];
    $('m-input').textContent = data.counts.input;
    $('m-accepted').textContent = data.counts.accepted;
    $('m-isolated').textContent = data.counts.isolated + data.counts.duplicates;
    $('m-rejected').textContent = data.summary.REJECT;
    renderRows(data);
    renderIssues(data);
    renderLedger(data);
    renderReconcile(data);
    renderCorrections(data);
    window.renderChart($('chart'), data.chart && data.chart.length ? (state.kind || 'bars') : 'bars', data.chart || []);
  }
  function stageButtons(stages) {
    $('stage-nav').innerHTML = stages.map(function (stage, index) {
      return '<button type="button" data-stage="' + stage.id + '" aria-pressed="' + (index === 0 ? 'true' : 'false') + '">' + esc(stage.name) + '</button>';
    }).join('');
    Array.from(document.querySelectorAll('[data-stage]')).forEach(function (button) {
      button.addEventListener('click', function () {
        document.querySelectorAll('[data-stage]').forEach(function (other) { other.setAttribute('aria-pressed', String(other === button)); });
        loadStage(button.getAttribute('data-stage'));
      });
    });
  }
  async function loadStage(stage) {
    try {
      setNotice('');
      document.body.setAttribute('aria-busy', 'true');
      var body = {profile: $('profile').value};
      if (state.run && state.run.run_id) body.run_id = state.run.run_id;
      var payload = await request('/api/stages/' + stage, {method: 'POST', body: JSON.stringify(body)});
      render(payload);
    } catch (error) { setNotice(error.message); }
    finally { document.body.removeAttribute('aria-busy'); }
  }
  function parseFixes() {
    var line = parseInt($('fix-line').value, 10);
    if (!line) throw new Error('请填写补正行号');
    var values = {};
    $('fix-values').value.split('\n').forEach(function (raw) {
      var text = raw.trim();
      if (!text) return;
      var split = text.split(/[=:：]/);
      if (split.length < 2) throw new Error('补正字段格式应为 字段=值');
      values[split[0].trim()] = split.slice(1).join('=').trim();
    });
    if (!Object.keys(values).length) throw new Error('请填写补正字段');
    return [{line: line, values: values}];
  }
  async function submitFix() {
    if (!state.run) { setNotice('请先执行批次'); return; }
    try {
      setNotice('');
      var fixes = parseFixes();
      var result = await request('/api/runs/' + state.run.run_id + '/corrections', {
        method: 'POST',
        body: JSON.stringify({fixes: fixes, comment: $('fix-comment').value})
      });
      state.run = result.run;
      state.approved = result.run.status === 'APPROVED';
      render(result.run);
      $('revision').textContent = 'rev ' + result.run.revision;
      $('run-status').textContent = result.run.status + ' · rev ' + result.run.revision;
      $('sign').disabled = result.run.summary.REJECT > 0 || state.approved;
      $('download').hidden = !state.approved;
      var fix = result.correction && result.correction.fixes[0];
      setNotice(result.created ? '补正已提交' : '补正重复提交，已忽略');
      if (fix && fix.status === 'REJECTED') setNotice('补正未生效：' + (fix.reason === 'SEGMENT_CLAIMED' ? '该测温段已有补正' : fix.reason));
    } catch (error) { setNotice(error.message); }
  }
  async function runBatch() {
    try {
      setNotice('');
      $('run').disabled = true;
      var run = await request('/api/runs', {method: 'POST', body: JSON.stringify({profile: $('profile').value})});
      state.run = run;
      state.approved = run.status === 'APPROVED';
      render(run);
      $('run-status').textContent = run.status + ' · rev ' + run.revision;
      $('revision').textContent = 'rev ' + run.revision;
      $('sign').disabled = run.summary.REJECT > 0 || state.approved;
      $('hold').disabled = state.approved;
      $('submit-fix').disabled = false;
      $('download').hidden = !state.approved;
      if (state.approved) $('download').href = '/api/runs/' + run.run_id + '/evidence';
    } catch (error) { setNotice(error.message); }
    finally { $('run').disabled = false; }
  }
  async function review(decision) {
    if (!state.run) return;
    try {
      var run = await request('/api/runs/' + state.run.run_id + '/review', {
        method: 'POST',
        body: JSON.stringify({decision: decision, comment: $('comment').value, expected_revision: state.run.revision})
      });
      state.run = run;
      state.approved = run.status === 'APPROVED';
      $('run-status').textContent = run.status + ' · rev ' + run.revision;
      $('revision').textContent = 'rev ' + run.revision;
      $('sign').disabled = true;
      $('hold').disabled = true;
      $('download').hidden = !state.approved;
      if (state.approved) $('download').href = '/api/runs/' + run.run_id + '/evidence';
    } catch (error) { setNotice(error.message); }
  }
  async function boot() {
    try {
      var catalog = await request('/api/catalog');
      state.kind = catalog.chart;
      state.resultColumns = catalog.result_columns;
      state.inputColumns = catalog.columns;
      stageButtons(catalog.stages.slice(0, 5));
      document.querySelector('.rail-note').textContent = catalog.code + ' · ' + catalog.stages[6].name;
      await loadStage('intake');
    } catch (error) { setNotice(error.message); }
    $('run').addEventListener('click', runBatch);
    $('sign').addEventListener('click', function () { review('APPROVED'); });
    $('hold').addEventListener('click', function () { review('HELD'); });
    $('submit-fix').addEventListener('click', submitFix);
    $('profile').addEventListener('change', function () {
      state.run = null; state.approved = false;
      $('sign').disabled = true; $('hold').disabled = true; $('download').hidden = true;
      $('submit-fix').disabled = true;
      $('run-status').textContent = '未执行批次'; $('revision').textContent = 'rev 0';
      loadStage('intake');
    });
  }
  document.addEventListener('DOMContentLoaded', boot);
})();
