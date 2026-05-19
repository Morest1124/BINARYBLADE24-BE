from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, FileResponse
import mimetypes
import os

from .models import FileAttachment
from utils.file_utils import validate_file, format_file_size
from .utils import get_target_user

class FileUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate file
        is_valid, detected_file_type, errors = validate_file(file_obj)
        if not is_valid:
            if errors:
                return Response({'error': errors[0]}, status=status.HTTP_400_BAD_REQUEST)
            return Response({'error': 'Invalid file'}, status=status.HTTP_400_BAD_REQUEST)

        # Determine category (usage)
        usage_category = 'other'
        requested_category = request.data.get('category')
        if requested_category:
            usage_category = requested_category.lower()

        description = request.data.get('description', '')

        try:
            target_user = get_target_user(request)
            attachment = FileAttachment.objects.create(
                user=target_user,
                file=file_obj,
                category=usage_category,
                file_type=detected_file_type,
                original_filename=file_obj.name,
                file_size=file_obj.size,
                description=description
            )
            
            return Response({
                'id': attachment.id,
                'url': attachment.file.url,
                'filename': attachment.original_filename,
                'category': attachment.category,
                'file_type': attachment.file_type,
                'size': format_file_size(attachment.file_size),
                'uploaded_at': attachment.uploaded_at
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            print(f"File Upload Error: {str(e)}") # Log error to console
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class FileListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        category = request.query_params.get('category')
        target_user = get_target_user(request)
        files = FileAttachment.objects.filter(user=target_user).order_by('-uploaded_at')
        
        if category:
            files = files.filter(category=category)
            
        data = []
        for f in files:
            data.append({
                'id': f.id,
                'url': f.file.url,
                'filename': f.original_filename,
                'category': f.category,
                'file_type': f.file_type,
                'size': f.get_file_size_display(),
                'uploaded_at': f.uploaded_at,
                'description': f.description
            })
            
        return Response(data)

class FileDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk, *args, **kwargs):
        file_attachment = get_object_or_404(FileAttachment, pk=pk)
        # Check permissions: owner or admin
        if file_attachment.user != request.user and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        
        file_attachment.file.delete()  # Delete actual file
        file_attachment.delete()       # Delete DB record
        return Response(status=status.HTTP_204_NO_CONTENT)

class FileDownloadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        file_attachment = get_object_or_404(FileAttachment, pk=pk)
        # Check permissions: owner or admin
        if file_attachment.user != request.user and not request.user.is_staff:
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        
        file_path = file_attachment.file.path
        
        if os.path.exists(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = 'application/octet-stream'
                
            response = FileResponse(open(file_path, 'rb'), content_type=mime_type)
            response['Content-Disposition'] = f'attachment; filename="{file_attachment.original_filename}"'
            return response
        else:
            return Response({'error': 'File not found'}, status=status.HTTP_404_NOT_FOUND)
