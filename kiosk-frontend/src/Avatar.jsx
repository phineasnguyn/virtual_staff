import React, { useRef, useEffect } from 'react';
import { useFrame } from '@react-three/fiber';
import { useGLTF, useAnimations } from '@react-three/drei';
import { useVoiceAssistant } from '@livekit/components-react';

export function Avatar(props) {
  const group = useRef();
  
  // Tải mô hình 3D (bạn cần đặt file avatar.glb vào thư mục public/)
  // Nếu chưa có file, nó sẽ bị lỗi. Tạm thời mình dùng fallback bên dưới nếu không tìm thấy file.
  const { nodes, materials, animations, scene } = useGLTF('/avatar.glb');
  const { actions } = useAnimations(animations, group);
  
  const { state, audioTrack } = useVoiceAssistant();
  
  // Biến lưu trữ góc xoay mục tiêu để tạo chuyển động mượt mà (lerp)
  const targetRotation = useRef({ x: 0, y: 0, z: 0 });

  // Xử lý animation khi AI đang nói
  useEffect(() => {
    if (state === 'speaking') {
      // Chạy animation nói chuyện (nếu có trong file glTF)
      if (actions && actions['Talking']) {
        actions['Talking'].play();
      }
    } else {
      if (actions && actions['Talking']) {
        actions['Talking'].stop();
      }
      // Chạy animation nhàn rỗi (Idle)
      if (actions && actions['Idle']) {
        actions['Idle'].play();
      }
    }
  }, [state, actions]);

  // Xử lý chuyển động (Cử chỉ) và khẩu hình miệng
  useFrame((renderState, delta) => {
    const time = renderState.clock.getElapsedTime();
    
    // 1. CHUYỂN ĐỘNG CƠ THỂ/ĐẦU
    // Tìm xương đầu (hỗ trợ nhiều chuẩn tên khác nhau)
    const head = scene.getObjectByName('Head') || scene.getObjectByName('mixamorigHead') || scene.getObjectByName('Head_M');
    
    if (state === 'thinking') {
      // TRẠNG THÁI: Đang suy nghĩ / Đang tra cứu dữ liệu
      // Hành động: Cúi đầu nhẹ xuống, lắc đầu qua lại như đang đọc hồ sơ
      targetRotation.current.x = 0.2 + Math.sin(time * 2) * 0.05; // Cúi xuống
      targetRotation.current.y = Math.sin(time * 3) * 0.15; // Đọc từ trái qua phải
    } else if (state === 'speaking') {
      // TRẠNG THÁI: Đang nói
      // Hành động: Nhìn thẳng, thỉnh thoảng gật gù nhẹ nhấn mạnh câu nói
      targetRotation.current.x = Math.sin(time * 5) * 0.03;
      targetRotation.current.y = Math.sin(time * 2) * 0.04;
    } else if (state === 'listening' || state === 'connected') {
      // TRẠNG THÁI: Đang nghe hoặc Nhàn rỗi
      // Hành động: Nhìn thẳng, hơi lắc lư tự nhiên (Idle)
      targetRotation.current.x = Math.sin(time * 1.5) * 0.02;
      targetRotation.current.y = Math.sin(time * 0.5) * 0.05;
    } else {
      targetRotation.current.x = 0;
      targetRotation.current.y = 0;
    }

    // Áp dụng góc xoay một cách mượt mà (Lerp)
    if (head) {
      head.rotation.x += (targetRotation.current.x - head.rotation.x) * delta * 4;
      head.rotation.y += (targetRotation.current.y - head.rotation.y) * delta * 4;
    }

    // 2. KHẨU HÌNH MIỆNG (LIP-SYNC)
    if (state === 'speaking' && audioTrack) {
      if (nodes && nodes.Wolf3D_Head && nodes.Wolf3D_Head.morphTargetDictionary) {
        const mouthOpenIndex = nodes.Wolf3D_Head.morphTargetDictionary['mouthOpen'];
        if (mouthOpenIndex !== undefined) {
          nodes.Wolf3D_Head.morphTargetInfluences[mouthOpenIndex] = Math.random() * 0.5 + 0.2;
        }
      }
    } else {
      if (nodes && nodes.Wolf3D_Head && nodes.Wolf3D_Head.morphTargetDictionary) {
        const mouthOpenIndex = nodes.Wolf3D_Head.morphTargetDictionary['mouthOpen'];
        if (mouthOpenIndex !== undefined) {
          // Khép miệng mượt mà
          nodes.Wolf3D_Head.morphTargetInfluences[mouthOpenIndex] *= 0.8;
        }
      }
    }
  });

  return (
    <group ref={group} {...props} dispose={null}>
      <primitive object={scene} />
    </group>
  );
}

// Hàm fallback hiển thị 1 khối cầu phát sáng nếu chưa có file avatar.glb
export function FallbackAvatar({ isSpeaking }) {
  const meshRef = useRef();
  
  useFrame((state) => {
    const time = state.clock.getElapsedTime();
    if (isSpeaking) {
      meshRef.current.scale.setScalar(1 + Math.sin(time * 10) * 0.1);
      meshRef.current.material.emissiveIntensity = 2 + Math.sin(time * 10);
    } else {
      meshRef.current.scale.setScalar(1 + Math.sin(time * 2) * 0.02);
      meshRef.current.material.emissiveIntensity = 0.5 + Math.sin(time * 2) * 0.2;
    }
  });

  return (
    <mesh ref={meshRef} position={[0, 0, 0]}>
      <sphereGeometry args={[1.5, 64, 64]} />
      <meshStandardMaterial 
        color="#14B8A6" 
        emissive="#14B8A6" 
        emissiveIntensity={1}
        wireframe={true}
      />
    </mesh>
  );
}

useGLTF.preload('/avatar.glb');
