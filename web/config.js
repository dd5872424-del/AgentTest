/**
 * 前端配置
 */
export const CONFIG = {
    // API 服务器地址
    API_BASE_URL: 'http://localhost:8000',
    
    // 默认图类型
    DEFAULT_GRAPH: 'roleplay',
    
    // 可用的图
    GRAPHS: [
        { name: 'default', label: '默认对话', description: '基础聊天' },
        { name: 'roleplay', label: '角色扮演', description: '带情绪追踪' },
        { name: 'with_commands', label: '指令模式', description: '支持 /设定 /记住 等指令' },
    ],
};
