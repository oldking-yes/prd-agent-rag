"""Add StatsPanel component to frontend HTML files."""
import re

CHART_CDN = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>'

STATS_PANEL = r"""
function StatsPanel({ onClose }) {
  const [summary, setSummary] = React.useState(null);
  const [daily, setDaily] = React.useState([]);
  const [rag, setRag] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const chartRef = React.useRef(null);
  const chartInstance = React.useRef(null);

  React.useEffect(() => {
    async function load() {
      try {
        const [sumRes, dailyRes, ragRes] = await Promise.all([
          apiFetch('/stats/summary?days=30'),
          apiFetch('/stats/daily?days=7'),
          apiFetch('/stats/rag?days=30'),
        ]);
        setSummary(sumRes);
        setDaily(dailyRes);
        setRag(ragRes);
      } catch(e) { console.error(e); }
      setLoading(false);
    }
    load();
  }, []);

  React.useEffect(() => {
    if (!daily.length || !chartRef.current) return;
    if (chartInstance.current) chartInstance.current.destroy();
    chartInstance.current = new Chart(chartRef.current, {
      type: 'bar',
      data: {
        labels: daily.map(d => d.date.slice(5)),
        datasets: [
          { label: '输入 tokens', data: daily.map(d => d.input_tokens), backgroundColor: 'rgba(99,102,241,0.7)' },
          { label: '输出 tokens', data: daily.map(d => d.output_tokens), backgroundColor: 'rgba(168,85,247,0.7)' },
        ]
      },
      options: { responsive: true, plugins: { legend: { labels: { color: '#94a3b8' } } }, scales: { x: { ticks: { color: '#64748b' } }, y: { ticks: { color: '#64748b' } } } }
    });
    return () => { if (chartInstance.current) chartInstance.current.destroy(); };
  }, [daily]);

  if (loading) return React.createElement('div', { className: 'modal-overlay', onClick: (e) => { if (e.target === e.currentTarget) onClose(); } },
    React.createElement('div', { className: 'modal-content' }, React.createElement('div', { style: { padding: 40, textAlign: 'center', color: 'var(--text-tertiary)' } }, '加载中...'))
  );

  const s = summary || {};
  const r = rag || {};

  return React.createElement('div', { className: 'modal-overlay', onClick: (e) => { if (e.target === e.currentTarget) onClose(); } },
    React.createElement('div', { className: 'modal-content', style: { maxWidth: 700 } },
      React.createElement('div', { className: 'modal-header' },
        React.createElement('h3', null, '用量统计'),
        React.createElement('button', { className: 'close-btn', onClick: onClose }, Icons.x)
      ),
      React.createElement('div', { className: 'modal-body' },
        React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 } },
          React.createElement('div', { style: { background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 8, padding: 12, textAlign: 'center' } },
            React.createElement('div', { style: { fontSize: 22, fontWeight: 700, color: 'var(--accent)' } }, (s.total_tokens || 0).toLocaleString()),
            React.createElement('div', { style: { fontSize: 11, color: 'var(--text-tertiary)' } }, '总 Tokens')
          ),
          React.createElement('div', { style: { background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 8, padding: 12, textAlign: 'center' } },
            React.createElement('div', { style: { fontSize: 22, fontWeight: 700, color: '#4ade80' } }, '¥' + (s.estimated_cost_cny || 0).toFixed(4)),
            React.createElement('div', { style: { fontSize: 11, color: 'var(--text-tertiary)' } }, '预估费用')
          ),
          React.createElement('div', { style: { background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 8, padding: 12, textAlign: 'center' } },
            React.createElement('div', { style: { fontSize: 22, fontWeight: 700, color: '#60a5fa' } }, s.total_requests || 0),
            React.createElement('div', { style: { fontSize: 11, color: 'var(--text-tertiary)' } }, '请求次数')
          ),
          React.createElement('div', { style: { background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 8, padding: 12, textAlign: 'center' } },
            React.createElement('div', { style: { fontSize: 22, fontWeight: 700, color: '#f59e0b' } }, (r.rag_trigger_rate || 0) + '%'),
            React.createElement('div', { style: { fontSize: 11, color: 'var(--text-tertiary)' } }, 'RAG 触发率')
          )
        ),
        React.createElement('div', { style: { background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 8, padding: 16, marginBottom: 20 } },
          React.createElement('div', { style: { fontSize: 13, fontWeight: 600, marginBottom: 8, color: 'var(--text-primary)' } }, '近 7 天 Token 趋势'),
          React.createElement('canvas', { ref: chartRef, height: 160 })
        ),
        React.createElement('div', { style: { background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 8, padding: 16 } },
          React.createElement('div', { style: { fontSize: 13, fontWeight: 600, marginBottom: 8, color: 'var(--text-primary)' } }, 'RAG 质量指标'),
          React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 13 } },
            React.createElement('div', null, React.createElement('span', { style: { color: 'var(--text-tertiary)' } }, '总请求: '), React.createElement('span', { style: { fontWeight: 600 } }, r.total_requests || 0)),
            React.createElement('div', null, React.createElement('span', { style: { color: 'var(--text-tertiary)' } }, 'RAG 触发: '), React.createElement('span', { style: { fontWeight: 600 } }, r.rag_triggered || 0)),
            React.createElement('div', null, React.createElement('span', { style: { color: 'var(--text-tertiary)' } }, '触发率: '), React.createElement('span', { style: { fontWeight: 600, color: '#4ade80' } }, (r.rag_trigger_rate || 0) + '%')),
            React.createElement('div', null, React.createElement('span', { style: { color: 'var(--text-tertiary)' } }, '输入 tokens: '), React.createElement('span', { style: { fontWeight: 600 } }, (s.input_tokens || 0).toLocaleString()))
          )
        )
      ),
      React.createElement('div', { className: 'modal-footer' },
        React.createElement('button', { className: 'btn btn-primary', onClick: onClose, style: { width: 'auto' } }, '关闭')
      )
    )
  );
}
"""

for fpath in ['frontend/index.html', 'frontend/public/index.html']:
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Add Chart.js CDN
    if 'chart.js' not in content:
        content = content.replace('</head>', CHART_CDN + '\n</head>')

    # 2. Add StatsPanel before NewConversationDialog
    if 'function StatsPanel' not in content:
        content = content.replace('function NewConversationDialog(', STATS_PANEL + '\nfunction NewConversationDialog(')

    # 3. Add stats button in Sidebar after KB button
    old_kb = "Icons.db, '知识库'"
    if old_kb in content and "用量统计" not in content:
        new_kb = old_kb + "),\n          React.createElement('button', { className: 'btn btn-secondary', onClick: () => window.__openStats && window.__openStats(), style: { marginTop: 8 } },\n            Icons.chart, '用量统计')"
        content = content.replace(old_kb, new_kb, 1)

    # 4. Add showStatsModal state
    if 'showStatsModal' not in content:
        content = content.replace(
            "const [showKBModal, setShowKBModal] = useState(false);",
            "const [showKBModal, setShowKBModal] = useState(false);\n  const [showStatsModal, setShowStatsModal] = useState(false);"
        )

    # 5. Add window.__openStats
    if 'window.__openStats' not in content:
        content = content.replace(
            'window.__openKB = () => setShowKBModal(true);',
            'window.__openKB = () => setShowKBModal(true);\n    window.__openStats = () => setShowStatsModal(true);'
        )

    # 6. Add StatsPanel render before KBModal render
    if 'showStatsModal && React.createElement(StatsPanel' not in content:
        content = content.replace(
            'showKBModal && React.createElement(KBModal',
            "showStatsModal && React.createElement(StatsPanel, { onClose: () => setShowStatsModal(false) }),\n        showKBModal && React.createElement(KBModal"
        )

    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'{fpath}: done')
