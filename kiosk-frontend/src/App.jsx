import React, { useState, Suspense } from 'react';
import {
  LiveKitRoom,
  RoomAudioRenderer,
  VoiceAssistantControlBar,
  useVoiceAssistant,
  DisconnectButton,
  Chat
} from '@livekit/components-react';
import '@livekit/components-styles';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Environment, ContactShadows } from '@react-three/drei';
import { Avatar, FallbackAvatar } from './Avatar';

function Scene() {
  const { state } = useVoiceAssistant();
  const isSpeaking = state === 'speaking';

  return (
    <>
      <ambientLight intensity={0.5} />
      <directionalLight position={[10, 10, 5]} intensity={1.5} />
      <Environment preset="city" />
      
      {/* Cố gắng tải Avatar 3D, nếu lỗi hoặc chưa có sẽ render Khối cầu ánh sáng */}
      <Suspense fallback={<FallbackAvatar isSpeaking={isSpeaking} />}>
        {/* Nếu bạn có file avatar.glb thực sự, bỏ comment dòng dưới và xóa FallbackAvatar */}
        <Avatar position={[0, 1.5, 0]} scale={1.2} />
        {/* <FallbackAvatar isSpeaking={isSpeaking} /> */}
      </Suspense>

      <ContactShadows opacity={0.4} scale={10} blur={2} far={4} position={[0, 0.5, 0]} />
      <OrbitControls target={[0, 1, 0]} enableZoom={true} enablePan={true} maxPolarAngle={Math.PI / 2 + 0.1} />
    </>
  );
}

function Header() {
  const { state } = useVoiceAssistant();
  
  return (
    <div className="w-full flex justify-between items-center glass-panel p-4 px-8 mb-4 shrink-0">
      <div>
        <h1 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-teal-300">
          Hệ Thống Trợ Lý Y Tế Ảo
        </h1>
        <p className="text-sm text-slate-300">Sẵn sàng phục vụ bạn</p>
      </div>
      <div className="flex items-center gap-3">
        <div className={`w-3 h-3 rounded-full ${state === 'connected' || state === 'speaking' || state === 'listening' ? 'bg-green-500 animate-pulse' : 'bg-yellow-500'}`}></div>
        <span className="text-sm font-medium uppercase tracking-wider text-slate-300">
          {state || 'Đang chờ...'}
        </span>
      </div>
    </div>
  );
}

function App() {
  const [roomConfig, setRoomConfig] = useState({
    serverUrl: import.meta.env.VITE_LIVEKIT_URL || '',
    token: import.meta.env.VITE_LIVEKIT_TOKEN || ''
  });

  const [isConnecting, setIsConnecting] = useState(false);

  const connectToRoom = (e) => {
    e.preventDefault();
    setIsConnecting(true);
  };

  // Màn hình chờ nhập thông tin LiveKit nếu chưa cấu hình
  if (!roomConfig.serverUrl || !roomConfig.token || !isConnecting) {
    return (
      <div className="w-full h-full flex items-center justify-center">
        <div className="glass-panel p-8 max-w-md w-full animate-in fade-in zoom-in duration-500">
          <h2 className="text-2xl font-bold mb-6 text-center text-teal-300">Bắt đầu phiên kết nối</h2>
          <form onSubmit={connectToRoom} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">LiveKit Server URL</label>
              <input 
                type="text" 
                required
                className="w-full px-4 py-2 rounded-lg bg-slate-800/50 border border-slate-600 text-white focus:outline-none focus:border-teal-400"
                value={roomConfig.serverUrl}
                onChange={(e) => setRoomConfig({...roomConfig, serverUrl: e.target.value})}
                placeholder="wss://your-project.livekit.cloud"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">Access Token</label>
              <input 
                type="password" 
                required
                className="w-full px-4 py-2 rounded-lg bg-slate-800/50 border border-slate-600 text-white focus:outline-none focus:border-teal-400"
                value={roomConfig.token}
                onChange={(e) => setRoomConfig({...roomConfig, token: e.target.value})}
                placeholder="eyJhbGciOiJIUzI1NiIsIn..."
              />
            </div>
            <button type="submit" className="w-full py-3 mt-4 bg-gradient-to-r from-blue-600 to-teal-500 hover:from-blue-500 hover:to-teal-400 rounded-lg font-bold shadow-lg shadow-teal-500/20 transition-all">
              Kết nối tới Avatar
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <LiveKitRoom
      serverUrl={roomConfig.serverUrl}
      token={roomConfig.token}
      connect={true}
      audio={true}
      video={false}
      className="w-full h-screen bg-slate-900 flex flex-col p-4 overflow-hidden"
      onDisconnected={() => setIsConnecting(false)}
    >
      {/* Render âm thanh phòng */}
      <RoomAudioRenderer />
      
      {/* Header phía trên */}
      <Header />

      {/* Bố cục chính: Trái Avatar, Phải Chat */}
      <div className="flex-1 w-full max-w-7xl mx-auto flex flex-col md:flex-row gap-6 min-h-0">
        
        {/* Khối Trái: Avatar 3D */}
        <div className="flex-[2] relative rounded-3xl glass-panel overflow-hidden flex flex-col shadow-2xl">
          <div className="absolute inset-0 z-0">
            <Canvas camera={{ position: [0, 0, 4], fov: 45 }}>
              <Scene />
            </Canvas>
          </div>
          
          {/* Thanh điều khiển đè lên dưới cùng của khối Avatar */}
          <div className="absolute bottom-6 left-0 right-0 flex justify-center items-center z-10 pointer-events-none">
            <div className="pointer-events-auto flex gap-4 items-center bg-slate-900/40 p-2 rounded-2xl backdrop-blur-md border border-white/10">
              <VoiceAssistantControlBar />
              <DisconnectButton className="px-4 py-2 bg-red-500/20 hover:bg-red-500/40 border border-red-500/50 text-red-200 rounded-lg transition-all font-medium">
                Ngắt kết nối
              </DisconnectButton>
            </div>
          </div>
        </div>

        {/* Khối Phải: Khung Chat */}
        <div className="flex-1 md:max-w-sm rounded-3xl glass-panel overflow-hidden flex flex-col shadow-2xl">
          <div className="p-4 border-b border-white/10 bg-black/20 flex-shrink-0">
            <h2 className="text-lg font-bold text-teal-300">Trò chuyện văn bản</h2>
          </div>
          {/* Vùng chứa Chat của LiveKit */}
          <div className="flex-1 relative chat-container-override">
            <Chat className="absolute inset-0 w-full h-full" />
          </div>
        </div>

      </div>
    </LiveKitRoom>
  );
}

export default App;
