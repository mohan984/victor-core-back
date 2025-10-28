# accounts/views.py
from django.shortcuts import render

# Create your views here.
from rest_framework.response import Response
from rest_framework import status, generics
from .serializers import SignupSerializer
from .serializers import UserProfileSerializer
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated # <-- This is key!
from rest_framework.decorators import api_view, permission_classes




class SignupView(generics.CreateAPIView):
    serializer_class = SignupSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "User created successfully!"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    


# accounts/views.py

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user_profile(request):
    serializer = UserProfileSerializer(request.user)
    return Response(serializer.data)





