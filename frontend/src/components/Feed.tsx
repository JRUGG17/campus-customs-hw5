import { useEffect, useRef, useState } from 'react'
import { AgentIcon, THEMES, isAgent } from '../agents'
import { nice } from '../lib'
import type { FeedItem } from '../lib'
import type { AgentName } from '../types'

function Speaker({ name }: { name: string }) {
  return isAgent(name) ? <><AgentIcon agent={name} size={16} /> <b>{THEMES[name].name}</b></> : <b>{name}</b>
}

function Bubble({ from, to, tag, children, kind }: { from: string; to?: string; tag?: string; children: React.ReactNode; kind?: string }) {
  const theme = isAgent(from) ? THEMES[from] : THEMES.boss
  return (
    <div className={`bubble ${theme.voice} ${kind ?? ''}`} style={{ ['--c' as string]: theme.color, ['--t' as string]: theme.tint }}>
      <div className="who">
        <Speaker name={from} />
        {to ? <> <span className="to">to</span> <Speaker name={to} /></> : null}
        <span className="tag">{tag ?? theme.tag}</span>
      </div>
      <div className="said">{children}</div>
    </div>
  )
}

function Item({ item }: { item: FeedItem }) {
  switch (item.kind) {
    case 'say':
      return <Bubble from={item.from} to={item.to}>{item.text}</Bubble>
    case 'report':
      return (
        <Bubble from={item.agent} tag="REPORT" kind="report">
          <p>{item.report.answer}</p>
          {(item.report.blockers?.length || item.report.needs_human?.length) ? (
            <div className="flags">
              {item.report.blockers?.map((b, i) => <span key={`b${i}`} className="flag block">blocked: {b}</span>)}
              {item.report.needs_human?.map((b, i) => <span key={`n${i}`} className="flag human">needs a human: {b}</span>)}
            </div>
          ) : null}
        </Bubble>
      )
    case 'boss_wrap':
      return <Bubble from="boss" tag="PRIORITY">{item.text}</Bubble>
    case 'tools': {
      const color = isAgent(item.agent) ? THEMES[item.agent as AgentName].color : '#00356b'
      return (
        <div className="act folded" style={{ ['--c' as string]: color }}>
          {isAgent(item.agent) && <AgentIcon agent={item.agent} size={14} />}
          <b>{nice(item.agent)}</b> looked things up:
          {item.tools.map(t => <code key={t}>{t}</code>)}
        </div>
      )
    }
    case 'act': {
      const color = isAgent(item.agent) ? THEMES[item.agent as AgentName].color : '#00356b'
      return (
        <div className="act" style={{ ['--c' as string]: color }}>
          {isAgent(item.agent) && <AgentIcon agent={item.agent} size={14} />}
          <b>{nice(item.agent)}</b> used <code>{item.tool}</code>{item.args ? <span className="args">({item.args})</span> : null}
        </div>
      )
    }
    case 'got':
      return <div className={`got ${item.bad ? 'bad' : ''}`} title={item.full}>↳ {item.gist || 'no data'}</div>
    case 'refused':
      return <div className="refused"><b>{nice(item.agent)}</b> was told no: {item.text}</div>
    case 'note':
      return <div className={`note ${item.bad ? 'bad' : ''}`}>{item.text}</div>
  }
}

export function Feed({ items, running }: { items: FeedItem[]; running: boolean }) {
  const box = useRef<HTMLDivElement>(null)
  const [stick, setStick] = useState(true)

  // Scroll the chat box itself. scrollIntoView would also scroll the whole page and yank it down here.
  useEffect(() => {
    const el = box.current
    if (stick && el) el.scrollTop = el.scrollHeight
  }, [items.length, stick])

  const onScroll = () => {
    const el = box.current
    if (el) setStick(el.scrollHeight - el.scrollTop - el.clientHeight < 60)
  }

  return (
    <div className="feed-wrap">
      <div className="feed" ref={box} onScroll={onScroll} aria-live="polite">
        {items.length === 0 && (
          <div className="quiet">
            <p>The floor is quiet.</p>
            <p className="muted">Pick a ticket and start the team. You'll see who is asked and what they say.</p>
          </div>
        )}
        {items.map((it, i) => <Item key={`${it.seq}-${i}`} item={it} />)}
        {running && <div className="typing" aria-label="The team is working"><i /><i /><i /></div>}
      </div>
      {!stick && (
        <button className="jump" onClick={() => { setStick(true); const el = box.current; if (el) el.scrollTop = el.scrollHeight }}>
          Jump to latest ↓
        </button>
      )}
    </div>
  )
}
