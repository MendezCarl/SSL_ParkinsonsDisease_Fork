import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import backgroundImage from '@/assets/tempBackground.png'; //change with actual image later

const Welcome = () => {
  const navigate = useNavigate();

  return (
    <div 
      className="min-h-screen bg-cover bg-center bg-no-repeat flex flex-col items-center justify-center p-4 relative"
      style={{ backgroundImage: `url(${backgroundImage})` }}
    >
      {/* Gray overlay */}
      <div className="absolute inset-0 bg-black/60" />
      
      <div className="relative z-10 flex flex-col items-center space-y-12">
        <h1 className="text-9xl font-bold text-white tracking-wider">
          Parkinson's Artificial Intelligence Diagnosis Tool
        </h1>
        
        {/* Buttons */}
        <div className="flex flex-col sm:flex-row gap-4">
          <Button 
            size="lg" 
            onClick={() => navigate('/login')}
            className="text-lg px-12 py-6"
          >
            Log In
          </Button>
          <Button 
            size="lg" 
            variant="outline"
            onClick={() => navigate('/register')}
            className="text-lg px-12 py-6 bg-white/10 backdrop-blur-sm border-white text-white hover:bg-white hover:text-black"
          >
            Sign Up
          </Button>
        </div>
      </div>
    </div>
  );
};

export default Welcome;