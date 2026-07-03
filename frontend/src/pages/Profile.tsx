import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Check, LogIn } from 'lucide-react';
import { Separator } from '@/components/ui/separator';
import { useAuth } from '@/auth/auth-context';

const Profile = () => {
  const navigate = useNavigate();
  const { user, isLoading, isAuthenticated } = useAuth();

  const profileData = useMemo(() => {
    if (!user) {
      return null;
    }

    const [firstName, ...rest] = user.fullName.split(' ');
    return {
      firstName: firstName || '',
      lastName: rest.join(' '),
      email: user.email || '',
      title: user.title,
      location: user.location,
      specialty: user.speciality,
    };
  }, [user]);

  const initials = useMemo(() => {
    if (!profileData) return 'DR';
    return `${profileData.firstName[0] || ''}${profileData.lastName[0] || profileData.firstName[1] || ''}`.toUpperCase();
  }, [profileData]);

  if (isLoading) {
    return <div className="min-h-screen flex items-center justify-center">Loading profile...</div>;
  }

  if (!isAuthenticated || !profileData) {
    return (
      <div className="min-h-screen bg-background py-8">
        <div className="container mx-auto px-6 max-w-2xl">
          <Card>
            <CardHeader>
              <CardTitle>Profile Settings</CardTitle>
              <CardDescription>Sign in to view your backend profile.</CardDescription>
            </CardHeader>
            <CardContent>
              <Button onClick={() => navigate('/login')}>
                <LogIn className="mr-2 h-4 w-4" />
                Go to Login
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background py-8">
      <div className="container mx-auto px-6 max-w-4xl">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-4">
              <div>
                <CardTitle className="text-2xl">Profile Settings</CardTitle>
                <CardDescription>Viewing account information from the backend.</CardDescription>
              </div>
              <Button onClick={() => navigate('/patients')}>
                <Check className="mr-2 h-4 w-4" />
                Done
              </Button>
            </div>
          </CardHeader>

          <CardContent className="space-y-6">
            <Alert>
              <AlertTitle>Read-only for now</AlertTitle>
              <AlertDescription>
                Profile editing is not connected to a backend update endpoint yet. The fields below are real account data, but changes cannot be saved yet.
              </AlertDescription>
            </Alert>

            <div className="flex flex-col items-center space-y-4">
              <Avatar className="h-32 w-32">
                <AvatarFallback className="text-2xl">{initials}</AvatarFallback>
              </Avatar>
              <div className="text-center">
                <h3 className="text-xl font-semibold">
                  {profileData.firstName} {profileData.lastName}
                </h3>
                <p className="text-sm text-muted-foreground">{profileData.title}</p>
              </div>
            </div>

            <Separator />

            <div className="space-y-4">
              <h4 className="text-lg font-semibold">Personal Information</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="firstName">First Name</Label>
                  <Input id="firstName" value={profileData.firstName} disabled />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="lastName">Last Name</Label>
                  <Input id="lastName" value={profileData.lastName} disabled />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="email">Email</Label>
                  <Input id="email" type="email" value={profileData.email} disabled />
                </div>
              </div>
            </div>

            <Separator />

            <div className="space-y-4">
              <h4 className="text-lg font-semibold">Professional Information</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="specialty">Specialty</Label>
                  <Input id="specialty" value={profileData.specialty} disabled />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="title">Title</Label>
                  <Input id="title" value={profileData.title} disabled />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="location">Location</Label>
                  <Input id="location" value={profileData.location} disabled />
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default Profile;
