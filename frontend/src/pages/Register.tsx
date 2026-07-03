import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useToast } from '@/hooks/use-toast';
import { Loader2, Check, X } from 'lucide-react';

const Register = () => {
  const navigate = useNavigate();
  const { toast } = useToast();

  //take all in as a string
  const [firstName, setFirstName] = useState(''); //combine to first and lat to make full name
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [location, setLocation] = useState('');
  const [title, setTitle] = useState(''); //maybe can be switched to a role
  const [department, setDepartment] = useState('');
  const [specialty, setSpecialty] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
        toast({
          title: 'Registration not connected yet',
          description: 'Backend account creation is not available in this demo yet. Use the demo login instead.',
        });
        navigate('/login');
    } catch (error) {
        console.error('Login failed', error);
    } finally {
        setIsLoading(false);
    }
  };

  const calculatePasswordStrength = (password: string) => {
    let strength = 0;
    const checks = {
      length: password.length >= 8,
      uppercase: /[A-Z]/.test(password),
      lowercase: /[a-z]/.test(password),
      number: /[0-9]/.test(password),
      special: /[!@#$%&*?]/.test(password),
    };

    if (checks.length) strength += 20;
    if (checks.uppercase) strength += 20;
    if (checks.lowercase) strength += 20;
    if (checks.number) strength += 20;
    if (checks.special) strength += 20;

    let label = 'Very Weak';
    let color = 'bg-red-500';
    
    if (strength >= 80) {
      label = 'Strong';
      color = 'bg-green-500';
    } else if (strength >= 60) {
      label = 'Good';
      color = 'bg-blue-500';
    } else if (strength >= 40) {
      label = 'Fair';
      color = 'bg-yellow-500';
    } else if (strength >= 20) {
      label = 'Weak';
      color = 'bg-orange-500';
    }

    return { strength, label, color, checks };
  };

  const passwordStrength = calculatePasswordStrength(password);

  return (
    <div className="flex flex-col items-center justify-center min-h-screen py-8">
      <Card className="w-full max-w-2xl">
        <CardHeader>
          <CardTitle>Sign Up</CardTitle>
          <CardDescription>Registration is not connected to the backend yet. Use the demo login to continue.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className = "space-y-4">
            <div className='grid grid-cols-2 gap-4'>            
              <div>
                <Label htmlFor="firstName">First Name</Label>
                <Input
                  id="firstName"
                  type="text"
                  placeholder="John"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  required
                />
              </div>
              <div>
                <Label htmlFor="lastName">Last Name</Label>
                <Input
                  id="lastName"
                  type="text"
                  placeholder="Doe"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  required
                />
              </div>
            </div>
              <div>
                <Label htmlFor='email'>Email</Label>
                <Input 
                  id="email"
                  type="email"
                  placeholder="doctor@hospital.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <div className='space-y-2'>
                <div>
                  <Label htmlFor='password'>Password</Label>
                  <Input 
                    id="password"
                    type="password"
                    placeholder='••••••••'
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                  {(
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Password strength:</span>
                    <span className={`font-medium ${
                      passwordStrength.strength >= 80 ? 'text-green-600' :
                      passwordStrength.strength >= 60 ? 'text-blue-600' :
                      passwordStrength.strength >= 40 ? 'text-yellow-600' :
                      'text-red-600'
                    }`}>
                      {passwordStrength.label}
                    </span>
                  </div>
                  <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                    <div 
                      className={`h-full transition-all duration-300 ${passwordStrength.color}`}
                      style={{ width: `${passwordStrength.strength}%` }}
                    />
                  </div>
                  <div className="text-xs space-y-1 text-muted-foreground">
                    <div className="flex items-center gap-1">
                      {passwordStrength.checks.length ? 
                        <Check className="h-3 w-3 text-green-600" /> : 
                        <X className="h-3 w-3 text-red-600" />
                      }
                      <span>At least 8 characters</span>
                    </div>
                    <div className="flex items-center gap-1">
                      {passwordStrength.checks.uppercase ? 
                        <Check className="h-3 w-3 text-green-600" /> : 
                        <X className="h-3 w-3 text-red-600" />
                      }
                      <span>One uppercase letter</span>
                    </div>
                    <div className="flex items-center gap-1">
                      {passwordStrength.checks.lowercase ? 
                        <Check className="h-3 w-3 text-green-600" /> : 
                        <X className="h-3 w-3 text-red-600" />
                      }
                      <span>One lowercase letter</span>
                    </div>
                    <div className="flex items-center gap-1">
                      {passwordStrength.checks.number ? 
                        <Check className="h-3 w-3 text-green-600" /> : 
                        <X className="h-3 w-3 text-red-600" />
                      }
                      <span>One number</span>
                    </div>
                    <div className="flex items-center gap-1">
                      {passwordStrength.checks.special ? 
                        <Check className="h-3 w-3 text-green-600" /> : 
                        <X className="h-3 w-3 text-red-600" />
                      }
                      <span>One special character (!@#$%&*?)</span>
                    </div>
                  </div>
                </div>
              )}
                </div>
              </div>
              <div>
                <Label htmlFor='department'>Department</Label>
                <Input 
                  id="department"
                  type="text"
                  placeholder="Neurology"
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                  required
                />
              </div>
              <div>
                <Label htmlFor='speciality'>Speciality</Label>
                <Input 
                  id="speciality"
                  type="text"
                  placeholder='Brain Disorders'
                  value = {specialty}
                  onChange={(e) => setSpecialty(e.target.value)}
                  required
                />
              </div>
              <div>
                <Label htmlFor='title'>Title</Label>
                <Input 
                  id="title"
                  type="text"
                  placeholder="MD, PhD"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  required
                />
              </div>
              <div>
                <Label htmlFor='location'>Location</Label>
                <Input 
                  id="location"
                  type="text"
                  placeholder="Boston, MA"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                />
              </div>
            <Button type="submit" disabled={isLoading} className="w-full">
              {isLoading ? (
                <Loader2 className="animate-spin" />
              ) : (
                'Create Account'
              )}
            </Button>
          </form>
        </CardContent>
        <CardContent className="pt-0">
          <div className="text-center text-sm text-muted-foreground">
            Already have an account?{' '}
            <Link to="/login" className="font-semibold text-primary hover:underline">
              Sign in
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default Register;
