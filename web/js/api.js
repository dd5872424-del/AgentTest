/**
 * API 客户端
 */
import { CONFIG } from '../config.js';

const API_BASE = CONFIG.API_BASE_URL;

/**
 * 发起 API 请求
 */
async function request(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const config = {
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
        ...options,
    };
    
    if (config.body && typeof config.body === 'object') {
        config.body = JSON.stringify(config.body);
    }
    
    const response = await fetch(url, config);
    
    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(error.detail || error.error || '请求失败');
    }
    
    return response.json();
}

// ============================================================
// 会话 API
// ============================================================

export const conversations = {
    /**
     * 列出所有会话
     */
    async list() {
        const data = await request('/api/conversations');
        return data.conversations;
    },
    
    /**
     * 创建会话
     */
    async create(graphName = 'default', title = null, contentRefs = null) {
        return request('/api/conversations', {
            method: 'POST',
            body: {
                graph_name: graphName,
                title,
                content_refs: contentRefs,
            },
        });
    },
    
    /**
     * 获取会话详情
     */
    async get(id) {
        return request(`/api/conversations/${id}`);
    },
    
    /**
     * 删除会话
     */
    async delete(id) {
        return request(`/api/conversations/${id}`, { method: 'DELETE' });
    },
    
    /**
     * 清空所有会话
     */
    async clear() {
        return request('/api/conversations', { method: 'DELETE' });
    },
};

// ============================================================
// 聊天 API
// ============================================================

export const chat = {
    /**
     * 获取消息历史
     */
    async getMessages(conversationId) {
        const data = await request(`/api/conversations/${conversationId}/messages`);
        return data.messages;
    },
    
    /**
     * 发送消息（流式）
     * @param {string} conversationId 
     * @param {string} message 
     * @param {Function} onChunk 收到内容片段时的回调
     * @param {Function} onDone 完成时的回调
     * @param {Function} onError 错误时的回调
     */
    sendMessage(conversationId, message, { onChunk, onDone, onError }) {
        const url = `${API_BASE}/api/conversations/${conversationId}/chat`;
        
        // 使用 fetch + ReadableStream 处理 SSE
        fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message }),
        }).then(async response => {
            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || '发送失败');
            }
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';
                
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            if (data.type === 'chunk' && onChunk) {
                                onChunk(data.content);
                            } else if (data.type === 'done' && onDone) {
                                onDone(data);
                            } else if (data.type === 'error' && onError) {
                                onError(new Error(data.error));
                            }
                        } catch (e) {
                            // 忽略解析错误
                        }
                    }
                }
            }
        }).catch(error => {
            if (onError) onError(error);
        });
    },
    
    /**
     * 发送消息（非流式）
     */
    async sendMessageSync(conversationId, message) {
        return request(`/api/conversations/${conversationId}/chat/sync`, {
            method: 'POST',
            body: { message },
        });
    },
    
    /**
     * 重新生成
     */
    regenerate(conversationId, { onChunk, onDone, onError }) {
        const url = `${API_BASE}/api/conversations/${conversationId}/regenerate`;
        
        fetch(url, { method: 'POST' }).then(async response => {
            if (!response.ok) {
                throw new Error('重新生成失败');
            }
            
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';
                
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            if (data.type === 'chunk' && onChunk) {
                                onChunk(data.content);
                            } else if (data.type === 'done' && onDone) {
                                onDone(data);
                            } else if (data.type === 'error' && onError) {
                                onError(new Error(data.error));
                            }
                        } catch (e) {
                            // 忽略解析错误
                        }
                    }
                }
            }
        }).catch(error => {
            if (onError) onError(error);
        });
    },
    
    /**
     * 编辑消息
     */
    async editMessage(conversationId, messageIndex, content) {
        return request(`/api/conversations/${conversationId}/messages/${messageIndex}`, {
            method: 'PUT',
            body: { content },
        });
    },
    
    /**
     * 删除消息
     */
    async deleteMessage(conversationId, messageIndex) {
        return request(`/api/conversations/${conversationId}/messages/${messageIndex}`, {
            method: 'DELETE',
        });
    },
};

// ============================================================
// 状态 API
// ============================================================

export const state = {
    /**
     * 获取完整状态
     */
    async get(conversationId) {
        const data = await request(`/api/conversations/${conversationId}/state`);
        return data.state;
    },
    
    /**
     * 编辑状态
     */
    async edit(conversationId, updates) {
        return request(`/api/conversations/${conversationId}/state`, {
            method: 'PUT',
            body: { updates },
        });
    },
    
    /**
     * 获取状态历史
     */
    async getHistory(conversationId, limit = 10) {
        const data = await request(`/api/conversations/${conversationId}/state/history?limit=${limit}`);
        return data.history;
    },
};

// ============================================================
// 内容资产 API
// ============================================================

export const contents = {
    /**
     * 获取支持的内容类型
     */
    async getTypes() {
        const data = await request('/api/contents/types');
        return data.types;
    },
    
    /**
     * 列出指定类型的内容
     */
    async list(type, scope = 'global', tags = null) {
        let url = `/api/contents/${type}?scope=${scope}`;
        if (tags) url += `&tags=${tags.join(',')}`;
        const data = await request(url);
        return data.items;
    },
    
    /**
     * 获取单个内容
     */
    async get(type, id, scope = 'global') {
        return request(`/api/contents/${type}/${id}?scope=${scope}`);
    },
    
    /**
     * 创建/更新内容
     */
    async save(type, id, data, scope = 'global', tags = null) {
        return request(`/api/contents/${type}`, {
            method: 'POST',
            body: { id, data, scope, tags },
        });
    },
    
    /**
     * 删除内容
     */
    async delete(type, id, scope = 'global') {
        return request(`/api/contents/${type}/${id}?scope=${scope}`, {
            method: 'DELETE',
        });
    },
    
    /**
     * 搜索内容
     */
    async search(type, keyword, scope = 'global') {
        const data = await request(`/api/contents/${type}/search/${keyword}?scope=${scope}`);
        return data.items;
    },
};

// ============================================================
// 工具函数
// ============================================================

export const api = {
    conversations,
    chat,
    state,
    contents,
    
    /**
     * 健康检查
     */
    async health() {
        return request('/api/health');
    },
    
    /**
     * 获取可用的图列表
     */
    async getGraphs() {
        const data = await request('/api/graphs');
        return data.graphs;
    },
};

export default api;
