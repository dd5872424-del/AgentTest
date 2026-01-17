/**
 * 侧边栏 - 会话列表管理
 */
import { conversations } from './api.js';
import { CONFIG } from '../config.js';

class Sidebar {
    constructor() {
        this.container = document.getElementById('conversation-list');
        this.currentId = null;
        this.conversations = [];
        this.onSelect = null;
    }
    
    /**
     * 初始化侧边栏
     */
    async init() {
        await this.refresh();
        this.bindEvents();
    }
    
    /**
     * 绑定事件
     */
    bindEvents() {
        // 新建会话按钮
        const newBtn = document.getElementById('new-conversation-btn');
        if (newBtn) {
            newBtn.addEventListener('click', () => this.createNew());
        }
        
        // 图选择
        const graphSelect = document.getElementById('graph-select');
        if (graphSelect) {
            // 填充选项
            graphSelect.innerHTML = CONFIG.GRAPHS.map(g => 
                `<option value="${g.name}" ${g.name === CONFIG.DEFAULT_GRAPH ? 'selected' : ''}>${g.label}</option>`
            ).join('');
        }
    }
    
    /**
     * 刷新会话列表
     */
    async refresh() {
        try {
            this.conversations = await conversations.list();
            this.render();
        } catch (error) {
            console.error('加载会话列表失败:', error);
            this.showError('加载失败');
        }
    }
    
    /**
     * 渲染会话列表
     */
    render() {
        if (!this.container) return;
        
        if (this.conversations.length === 0) {
            this.container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-text">暂无会话</div>
                </div>
            `;
            return;
        }
        
        this.container.innerHTML = this.conversations.map(conv => `
            <div class="conversation-item ${conv.id === this.currentId ? 'active' : ''}" 
                 data-id="${conv.id}">
                <div class="conversation-item-title">${this.escapeHtml(conv.title)}</div>
                <div class="conversation-item-meta">
                    <span class="tag tag-cyan">${this.getGraphLabel(conv.graph_name)}</span>
                </div>
            </div>
        `).join('');
        
        // 绑定点击事件
        this.container.querySelectorAll('.conversation-item').forEach(item => {
            item.addEventListener('click', () => {
                const id = item.dataset.id;
                this.select(id);
            });
            
            // 右键菜单
            item.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                this.showContextMenu(e, item.dataset.id);
            });
        });
    }
    
    /**
     * 选择会话
     */
    select(id) {
        this.currentId = id;
        this.render();
        
        const conv = this.conversations.find(c => c.id === id);
        if (this.onSelect && conv) {
            this.onSelect(conv);
        }
    }
    
    /**
     * 创建新会话
     */
    async createNew() {
        const graphSelect = document.getElementById('graph-select');
        const graphName = graphSelect?.value || CONFIG.DEFAULT_GRAPH;
        const graphLabel = this.getGraphLabel(graphName);
        
        try {
            const conv = await conversations.create(graphName, `${graphLabel} 会话`);
            await this.refresh();
            this.select(conv.id);
        } catch (error) {
            console.error('创建会话失败:', error);
            this.showToast('创建失败: ' + error.message, 'error');
        }
    }
    
    /**
     * 删除会话
     */
    async delete(id) {
        if (!confirm('确定删除这个会话吗？')) return;
        
        try {
            await conversations.delete(id);
            if (this.currentId === id) {
                this.currentId = null;
                if (this.onSelect) {
                    this.onSelect(null);
                }
            }
            await this.refresh();
            this.showToast('会话已删除', 'success');
        } catch (error) {
            console.error('删除会话失败:', error);
            this.showToast('删除失败: ' + error.message, 'error');
        }
    }
    
    /**
     * 显示右键菜单
     */
    showContextMenu(event, id) {
        // 移除现有菜单
        const existing = document.querySelector('.context-menu');
        if (existing) existing.remove();
        
        const menu = document.createElement('div');
        menu.className = 'context-menu';
        menu.style.cssText = `
            position: fixed;
            left: ${event.clientX}px;
            top: ${event.clientY}px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
            padding: var(--space-xs);
            z-index: 1000;
            min-width: 120px;
        `;
        
        menu.innerHTML = `
            <button class="context-menu-item" data-action="delete">
                🗑️ 删除会话
            </button>
        `;
        
        document.body.appendChild(menu);
        
        // 点击菜单项
        menu.querySelector('[data-action="delete"]').addEventListener('click', () => {
            this.delete(id);
            menu.remove();
        });
        
        // 点击其他地方关闭
        const close = (e) => {
            if (!menu.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', close);
            }
        };
        setTimeout(() => document.addEventListener('click', close), 0);
    }
    
    /**
     * 获取图的显示名称
     */
    getGraphLabel(name) {
        const graph = CONFIG.GRAPHS.find(g => g.name === name);
        return graph?.label || name;
    }
    
    /**
     * HTML 转义
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    /**
     * 显示错误
     */
    showError(message) {
        if (this.container) {
            this.container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-text" style="color: var(--accent-pink)">
                        ${this.escapeHtml(message)}
                    </div>
                </div>
            `;
        }
    }
    
    /**
     * 显示提示
     */
    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        document.body.appendChild(toast);
        
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });
        
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }
}

export const sidebar = new Sidebar();
export default sidebar;
