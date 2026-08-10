// 层级文件树(niko:soul 多时不能满屏并列,要 hierarchy)——
// 世界工坊与角色工坊共用。
import type { TreeFile } from './localClient'

export type TreeDir = { name: string; path: string; children: TreeDir[]; files: TreeFile[] }

export function buildTree(list: TreeFile[]): TreeDir {
  const root: TreeDir = { name: '', path: '', children: [], files: [] }
  const dirAt = new Map<string, TreeDir>([['', root]])
  const ensure = (path: string): TreeDir => {
    const hit = dirAt.get(path)
    if (hit) return hit
    const parentPath = path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : ''
    const parent = ensure(parentPath)
    const node: TreeDir = { name: path.slice(path.lastIndexOf('/') + 1), path, children: [], files: [] }
    parent.children.push(node)
    dirAt.set(path, node)
    return node
  }
  for (const f of list) {
    const dir = f.path.includes('/') ? f.path.slice(0, f.path.lastIndexOf('/')) : ''
    ensure(dir).files.push(f)
  }
  const sortRec = (n: TreeDir) => {
    n.children.sort((a, b) => a.name.localeCompare(b.name))
    n.files.sort((a, b) => a.path.localeCompare(b.path))
    n.children.forEach(sortRec)
  }
  sortRec(root)
  return root
}

export function TreeView({
  node, depth, openDirs, toggle, sel, onOpen,
}: {
  node: TreeDir
  depth: number
  openDirs: Set<string>
  toggle: (d: string) => void
  sel: string
  onOpen: (p: string) => void
}) {
  return (
    <>
      {node.children.map((c) => {
        const open = openDirs.has(c.path)
        return (
          <div key={c.path}>
            <button
              onClick={() => toggle(c.path)}
              className="w-full text-left py-0.5 font-mono cursor-pointer border-0 bg-transparent truncate"
              style={{ color: 'var(--lc-dim)', paddingLeft: 8 + depth * 12 }}
              title={c.path}
            >
              {open ? '▾' : '▸'} {c.name}/
            </button>
            {open && (
              <TreeView node={c} depth={depth + 1} openDirs={openDirs} toggle={toggle} sel={sel} onOpen={onOpen} />
            )}
          </div>
        )
      })}
      {node.files.map((f) => (
        <button
          key={f.path}
          onClick={() => onOpen(f.path)}
          className="w-full text-left pr-2 py-0.5 font-mono truncate cursor-pointer border-0 bg-transparent"
          style={{
            color: sel === f.path ? 'var(--lc-candle)' : 'var(--lc-text)',
            paddingLeft: 8 + (depth + 1) * 12,
          }}
          title={f.path}
        >
          {f.path.slice(f.path.lastIndexOf('/') + 1)}
        </button>
      ))}
    </>
  )
}
